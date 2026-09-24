"""
SQLite 数据库模型：管理用户信息
"""

import sqlite3
from typing import Optional, List, Dict, Any
from datetime import datetime

from model.base import BaseModel


class UserModel(BaseModel):
    """用户模型类，提供用户信息的 CRUD 接口"""

    def __init__(self, db_path: str = "citation_analysis.db"):
        if db_path != self.DB_PATH:
            self._db_path_override = db_path
        else:
            self._db_path_override = None
        self._override_conn = None  # will be set by _get_connection()
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
                    conn.execute("PRAGMA foreign_keys = ON;")
                    BaseModel._override_pool[path] = conn
                self._override_conn = BaseModel._override_pool[path]
            return self._override_conn
        return super()._get_conn()

    def _init_database(self):
        conn = self._get_connection()
        cursor = conn.cursor()

        # ---------------- users 表 ----------------
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nickname TEXT NOT NULL,
                email TEXT,
                scholar_id TEXT,
                password TEXT NOT NULL,
                token TEXT,
                token_expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_nickname_unique ON users(nickname)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_scholar_id ON users(scholar_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_token ON users(token)")

        conn.commit()

    def close(self):
        pass

    # ==================== users 表：增删改查 ====================

    def add_user(
        self,
        nickname: str,
        password: str,
        email: Optional[str] = None,
        scholar_id: Optional[str] = None,
        token: Optional[str] = None,
        token_expires_at: Optional[datetime] = None,
    ) -> int:
        """
        添加新用户
        """
        token_expires_str = token_expires_at.isoformat() if token_expires_at else None

        def _do(cur):
            cur.execute("""
                INSERT INTO users
                (nickname, email, scholar_id, password, token, token_expires_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                nickname,
                email,
                scholar_id,
                password,
                token,
                token_expires_str,
            ))
            return cur.lastrowid

        return BaseModel.with_retry(_do, conn=self._get_connection())

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """根据用户id获取用户信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        if data.get("token_expires_at"):
            try:
                data["token_expires_at"] = datetime.fromisoformat(data["token_expires_at"])
            except (ValueError, TypeError):
                pass
        return data

    def get_user_by_nickname(self, nickname: str) -> Optional[Dict[str, Any]]:
        """根据昵称获取用户信息（昵称全局唯一）"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE nickname = ?", (nickname,))
        row = cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        if data.get("token_expires_at"):
            try:
                data["token_expires_at"] = datetime.fromisoformat(data["token_expires_at"])
            except (ValueError, TypeError):
                pass
        return data

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """根据邮箱获取用户信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        if data.get("token_expires_at"):
            try:
                data["token_expires_at"] = datetime.fromisoformat(data["token_expires_at"])
            except (ValueError, TypeError):
                pass
        return data

    def get_user_by_scholar_id(self, scholar_id: str) -> Optional[Dict[str, Any]]:
        """根据学者id获取用户信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE scholar_id = ?", (scholar_id,))
        row = cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        if data.get("token_expires_at"):
            try:
                data["token_expires_at"] = datetime.fromisoformat(data["token_expires_at"])
            except (ValueError, TypeError):
                pass
        return data

    def get_user_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """根据token获取用户信息；token过期返回 None"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE token = ?", (token,))
        row = cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        if data.get("token_expires_at"):
            try:
                expires_at = datetime.fromisoformat(data["token_expires_at"])
                if datetime.now() > expires_at:
                    return None
                data["token_expires_at"] = expires_at
            except (ValueError, TypeError):
                pass
        return data

    def update_user(self, user_id: int, **kwargs) -> bool:
        """更新用户信息"""
        allowed_fields = [
            "nickname", "email", "scholar_id", "password",
            "token", "token_expires_at",
        ]
        updates = []
        values = []

        for field, value in kwargs.items():
            if field not in allowed_fields:
                continue
            if field == "token_expires_at" and value is not None:
                if isinstance(value, datetime):
                    value = value.isoformat()
                elif not isinstance(value, str):
                    continue
            updates.append(f"{field} = ?")
            values.append(value)

        if not updates:
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(user_id)

        def _do(cur):
            cur.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                values,
            )
            return cur.rowcount > 0

        return BaseModel.with_retry(_do, conn=self._get_connection())

    def delete_user(self, user_id: int) -> bool:
        """删除用户"""
        def _do(cur):
            cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cur.rowcount > 0

        return BaseModel.with_retry(_do, conn=self._get_connection())

    def list_users(self) -> List[Dict[str, Any]]:
        """获取所有用户列表"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
        rows = cursor.fetchall()
        results = []
        for row in rows:
            data = dict(row)
            if data.get("token_expires_at"):
                try:
                    data["token_expires_at"] = datetime.fromisoformat(data["token_expires_at"])
                except (ValueError, TypeError):
                    pass
            results.append(data)
        return results

    def verify_password(self, user_id: int, password: str) -> bool:
        """验证用户密码"""
        user = self.get_user(user_id)
        if not user:
            return False
        return user.get("password") == password

    def update_token(self, user_id: int, token: str, expires_at: Optional[datetime] = None) -> bool:
        """更新用户token"""
        return self.update_user(user_id, token=token, token_expires_at=expires_at)

    def clear_token(self, user_id: int) -> bool:
        """清除用户token"""
        return self.update_user(user_id, token=None, token_expires_at=None)
