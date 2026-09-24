"""
SQLite 数据库模型：管理论文信息
- 仅包含 papers 表
- 不存 PDF / JSON 文件内容，只存路径
- 支持自动 schema migration（新增字段）
- 多用户隔离：papers 表含 user_id，查询/更新/删除时可按 user_id 过滤
"""

import sqlite3
import json
from typing import Optional, List, Dict, Any

from model.base import BaseModel


class DatabaseModel(BaseModel):
    """数据库模型类，提供 papers 表的 CRUD 接口（支持按 user_id 多用户隔离）"""

    # ==================== Schema 定义（单一真源） ====================

    PAPERS_SCHEMA = {
        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "user_id": "INTEGER",
        "title": "TEXT NOT NULL",
        "result_id": "TEXT",
        "link": "TEXT",
        "summary": "TEXT",
        "cite_link": "TEXT",
        "approach_name": "TEXT",
        "authors": "TEXT",
        "citation_number": "INTEGER DEFAULT -1",
        "year": "INTEGER",
        "venue": "TEXT",
        "analysis_status": "TEXT",
        "analysis_error": "TEXT",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }

    # ==================== 初始化 ====================

    def __init__(self, db_path: str = "citation_analysis.db"):
        # 兼容旧 API（允许传入 db_path）；实际连接由 BaseModel 单例托管。
        # 注意：BaseModel.DB_PATH 在类加载时被绑定；子类用与默认值不同的
        # db_path 时，会落到 _db_path_override 分支（独立连接，不共享单例）。
        if db_path != self.DB_PATH:
            self._db_path_override = db_path
        else:
            self._db_path_override = None
        # override 路径下的连接缓存（避免每次 _get_connection() 都新建）
        self._override_conn = None
        self._init_database()

    # ==================== 数据库连接 ====================

    def _get_connection(self):
        if getattr(self, "_db_path_override", None):
            path = self._db_path_override
            with BaseModel._init_lock:
                if path not in BaseModel._override_pool:
                    conn = sqlite3.connect(
                        path,
                        check_same_thread=False,
                        timeout=30,
                        isolation_level=None,
                    )
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA journal_mode=WAL;")
                    conn.execute("PRAGMA busy_timeout=30000;")
                    conn.execute("PRAGMA synchronous=NORMAL;")
                    BaseModel._override_pool[path] = conn
                self._override_conn = BaseModel._override_pool[path]
            return self._override_conn
        return super()._get_conn()

    # ==================== Schema Migration ====================

    def _get_existing_columns(self, table_name: str) -> set:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        return {row["name"] for row in cursor.fetchall()}

    def _migrate_table(self, table_name: str, schema: Dict[str, str]):
        existing_columns = self._get_existing_columns(table_name)

        def _do(cur):
            for column, definition in schema.items():
                if column not in existing_columns:
                    cur.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN {column} {definition}"
                    )

        BaseModel.with_retry(_do, conn=self._get_connection())

    def _init_database(self):
        conn = self._get_connection()
        cursor = conn.cursor()

        # 保证表存在（最小结构）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT
            )
        """)

        # 在 CREATE 之后再读取一次现有列，确保迁移判断准确
        cursor.execute(f"PRAGMA table_info(papers)")
        existing = {row["name"] for row in cursor.fetchall()}

        def _do(cur):
            for column, definition in self.PAPERS_SCHEMA.items():
                if column not in existing:
                    cur.execute(
                        f"ALTER TABLE papers ADD COLUMN {column} {definition}"
                    )

        BaseModel.with_retry(_do, conn=self._get_connection())

        # 索引
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_papers_title ON papers(title)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_papers_user_id ON papers(user_id)"
        )

        conn.commit()

    # ==================== papers 表：增删改查 ====================

    def add_paper(
        self,
        title: str,
        user_id: Optional[int] = None,
        result_id: Optional[str] = None,
        link: Optional[str] = None,
        summary: Optional[str] = None,
        cite_link: Optional[str] = None,
        approach_name: Optional[List[str]] = None,
        authors: Optional[List[str]] = None,
        citation_number: Optional[int] = None,
        year: Optional[int] = None,
        venue: Optional[str] = None,
        analysis_status: Optional[str] = "CREATED",
    ) -> int:
        def _do(cur):
            cur.execute("""
                INSERT INTO papers
                (user_id, title, result_id, link, summary, cite_link,
                 approach_name, authors, citation_number,
                 year, venue, analysis_status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                user_id,
                title,
                result_id,
                link,
                summary,
                cite_link,
                json.dumps(approach_name) if approach_name is not None else None,
                json.dumps(authors) if authors is not None else None,
                citation_number if citation_number is not None else -1,
                year,
                venue,
                analysis_status,
            ))
            return cur.lastrowid

        return self.with_retry(_do)

    def get_paper(
        self, paper_id: int, user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        根据 id 获取论文。若传入 user_id，则仅当该论文属于该用户时返回（多用户隔离）。
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        if user_id is not None:
            cursor.execute(
                "SELECT * FROM papers WHERE id = ? AND user_id = ?",
                (paper_id, user_id),
            )
        else:
            cursor.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
        row = cursor.fetchone()
        if not row:
            return None

        data = dict(row)
        if data.get("approach_name"):
            data["approach_name"] = json.loads(data["approach_name"])
        if data.get("authors"):
            data["authors"] = json.loads(data["authors"])
        return data

    def get_paper_id_by_title(
        self, title: str, user_id: Optional[int] = None
    ) -> Optional[int]:
        """
        根据标题获取论文 id。若传入 user_id，仅在该用户的论文中查找（多用户隔离）。
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        if user_id is not None:
            cursor.execute(
                "SELECT id FROM papers WHERE title = ? AND user_id = ?",
                (title, user_id),
            )
        else:
            cursor.execute("SELECT id FROM papers WHERE title = ?", (title,))
        row = cursor.fetchone()
        return row["id"] if row else None

    def update_paper(
        self, paper_id: int, user_id: Optional[int] = None, **kwargs
    ) -> bool:
        """
        更新论文。若传入 user_id，则仅当该论文属于该用户时才更新（多用户隔离）。
        """
        allowed_fields = {
            "title",
            "result_id",
            "link",
            "summary",
            "cite_link",
            "approach_name",
            "authors",
            "citation_number",
            "year",
            "venue",
            "analysis_status",
            "analysis_error",
        }

        updates = []
        values = []

        for field, value in kwargs.items():
            if field not in allowed_fields:
                continue

            if field in ("approach_name", "authors") and value is not None:
                value = json.dumps(value)

            updates.append(f"{field} = ?")
            values.append(value)

        if not updates:
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(paper_id)
        if user_id is not None:
            values.append(user_id)

        where_clause = "id = ? AND user_id = ?" if user_id is not None else "id = ?"

        def _do(cur):
            cur.execute(
                f"UPDATE papers SET {', '.join(updates)} WHERE {where_clause}",
                values,
            )
            return cur.rowcount > 0

        return self.with_retry(_do)

    def delete_paper(
        self, paper_id: int, user_id: Optional[int] = None
    ) -> bool:
        """
        删除论文。若传入 user_id，则仅当该论文属于该用户时才删除（多用户隔离）。
        """
        def _do(cur):
            if user_id is not None:
                cur.execute(
                    "DELETE FROM papers WHERE id = ? AND user_id = ?",
                    (paper_id, user_id),
                )
            else:
                cur.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
            return cur.rowcount > 0

        return self.with_retry(_do)

    def list_papers(
        self, user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        列出论文。若传入 user_id，仅返回该用户的论文（多用户隔离）；不传则返回全部。
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        if user_id is not None:
            cursor.execute(
                "SELECT * FROM papers WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
        else:
            cursor.execute("SELECT * FROM papers ORDER BY created_at DESC")
        rows = cursor.fetchall()

        results = []
        for row in rows:
            data = dict(row)
            if data.get("approach_name"):
                data["approach_name"] = json.loads(data["approach_name"])
            if data.get("authors"):
                data["authors"] = json.loads(data["authors"])
            results.append(data)

        return results
