"""
SQLite 共享基类：单例连接 + WAL + busy_timeout + 锁重试。

解决问题：
- 多线程下各 model 各自开连接 -> 文件级写锁争抢
- 默认 5s busy_timeout 太短 -> "database is locked"
- 默认 DELETE 日志模式 -> 读阻塞写

策略：
- 每进程对同一 DB 仅持有一个 sqlite3.Connection（check_same_thread=False 允许跨线程）
- 启用 WAL，读者不阻塞写者
- 设置 busy_timeout=30000 让 sqlite 内部先等
- 业务层在写时额外做指数退避重试
"""

from __future__ import annotations

import logging
import random
import sqlite3
import threading
import time
from typing import Any, Callable, Optional, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


class BaseModel:
    """所有 model 的基类，封装 SQLite 连接与重试。"""

    DB_PATH: str = "citation_analysis.db"
    BUSY_TIMEOUT_MS: int = 30_000
    WRITE_RETRIES: int = 6  # 业务层重试次数（与 busy_timeout 配合）
    _instance: Optional[sqlite3.Connection] = None
    _init_lock: threading.Lock = threading.Lock()
    _warmed: bool = False
    # 按路径缓存 override 连接，同路径共享同一连接（支持 FK 约束）。
    _override_pool: dict[str, sqlite3.Connection] = {}

    # ---------------- 连接管理（单例） ----------------

    @classmethod
    def _get_conn(cls) -> sqlite3.Connection:
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    conn = sqlite3.connect(
                        cls.DB_PATH,
                        check_same_thread=False,
                        timeout=cls.BUSY_TIMEOUT_MS / 1000,
                        isolation_level=None,  # autocommit；需要事务时显式 BEGIN
                    )
                    conn.row_factory = sqlite3.Row
                    # WAL 模式：读写并发友好
                    conn.execute("PRAGMA journal_mode=WAL;")
                    conn.execute("PRAGMA synchronous=NORMAL;")
                    conn.execute(f"PRAGMA busy_timeout={cls.BUSY_TIMEOUT_MS};")
                    conn.execute("PRAGMA foreign_keys=ON;")
                    cls._instance = conn
        return cls._instance

    @classmethod
    def _warm_pragmas(cls) -> None:
        """首次使用时确保 PRAGMA 已生效（部分 driver 需先写一次）"""
        if cls._warmed:
            return
        try:
            cur = cls._get_conn().cursor()
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute(f"PRAGMA busy_timeout={cls.BUSY_TIMEOUT_MS};")
            cur.execute("PRAGMA synchronous=NORMAL;")
            cur.execute("PRAGMA foreign_keys=ON;")
            cls._warmed = True
        except Exception as exc:  # pragma: no cover
            log.warning("warm pragmas failed: %s", exc)

    @classmethod
    def close(cls) -> None:
        """进程退出时关闭连接（可选）。"""
        with cls._init_lock:
            if cls._instance is not None:
                try:
                    cls._instance.close()
                except Exception:
                    pass
                cls._instance = None
                cls._warmed = False

    # ---------------- 写操作重试 ----------------

    @classmethod
    def with_retry(
        cls,
        fn: Callable[[sqlite3.Cursor], T],
        *,
        max_attempts: Optional[int] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> T:
        """
        执行 fn(cursor)；遇 'database is locked' / 'SQLITE_BUSY' 指数退避重试。

        使用方式::

            BaseModel.with_retry(lambda cur: cur.execute(...))

        默认隔离级别为 autocommit（isolation_level=None）；如需事务，
        请在 fn 内显式执行 ``cur.execute("BEGIN")`` / ``COMMIT`` / ``ROLLBACK``，
        并保证短事务。

        参数:
            fn: 需要执行的回调，参数是新创建的 cursor。
            max_attempts: 最大重试次数。
            conn: 可选，传入要使用的连接；不传则调用 ``_get_connection()``。
        """
        cls._warm_pragmas()
        attempts = max_attempts or cls.WRITE_RETRIES
        last_exc: Optional[Exception] = None

        # 选择连接：若调用方提供了 conn 就用它；否则退回 BaseModel 单例。
        # 调用方应显式传入 conn=，避免落到 BaseModel 单例。
        use_conn = conn
        if use_conn is None:
            use_conn = cls._get_conn()

        for i in range(attempts):
            cur = use_conn.cursor()
            try:
                result = fn(cur)
                return result
            except sqlite3.OperationalError as exc:
                msg = str(exc).lower()
                if "locked" not in msg and "busy" not in msg:
                    raise
                last_exc = exc
                wait = min(0.1 * (2 ** i), 5.0) + random.uniform(0, 0.05)
                log.warning(
                    "sqlite busy/locked (%s), retry %d/%d in %.2fs",
                    exc, i + 1, attempts, wait,
                )
                try:
                    cur.close()
                except Exception:
                    pass
                time.sleep(wait)
            except Exception:
                try:
                    cur.close()
                except Exception:
                    pass
                raise

        raise RuntimeError(
            f"sqlite still locked after {attempts} retries: {last_exc}"
        )
