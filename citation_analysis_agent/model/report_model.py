"""
SQLite 数据库模型：管理报告信息
- 表 reports：id 主键，user_id 多用户隔离
- 支持自动 schema migration（新增字段）
"""

import sqlite3
import json
from typing import Optional, List, Dict, Any

from model.base import BaseModel


class ReportModel(BaseModel):
    """报告模型类，提供 reports 表的 CRUD 接口"""

    # ==================== Schema 定义（单一真源） ====================

    REPORTS_SCHEMA = {
        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "user_id": "INTEGER",
        "name": "TEXT",
        "paper_ids": "TEXT",
        "paper_count": "INTEGER DEFAULT 0",
        "status": "TEXT",
        "html_path": "TEXT",
        "pdf_path": "TEXT",
        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    }

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

        self.with_retry(_do)

    def _init_database(self):
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT
            )
        """)

        cursor.execute("PRAGMA table_info(reports)")
        existing = {row["name"] for row in cursor.fetchall()}

        def _do(cur):
            for column, definition in self.REPORTS_SCHEMA.items():
                if column not in existing:
                    cur.execute(
                        f"ALTER TABLE reports ADD COLUMN {column} {definition}"
                    )

        self.with_retry(_do)

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_user_id ON reports(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status)"
        )

        conn.commit()

    def close(self):
        pass

    # ==================== 辅助 ====================

    def _row_to_dict(self, row) -> Dict[str, Any]:
        data = dict(row)
        if data.get("paper_ids") is not None and data["paper_ids"]:
            try:
                data["paper_ids"] = json.loads(data["paper_ids"])
            except (json.JSONDecodeError, TypeError):
                data["paper_ids"] = []
        return data

    # ==================== 增删改查 ====================

    def add_report(
        self,
        user_id: int,
        name: str,
        paper_ids: Optional[List[int]] = None,
        paper_count: Optional[int] = None,
        status: Optional[str] = "pending",
        html_path: Optional[str] = None,
        pdf_path: Optional[str] = None,
    ) -> int:
        """添加一条报告记录"""
        ids = paper_ids if paper_ids is not None else []
        count = paper_count if paper_count is not None else len(ids)
        paper_ids_json = json.dumps(ids)

        def _do(cur):
            cur.execute("""
                INSERT INTO reports
                (user_id, name, paper_ids, paper_count, status, html_path, pdf_path, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                user_id,
                name,
                paper_ids_json,
                count,
                status,
                html_path,
                pdf_path,
            ))
            return cur.lastrowid

        return BaseModel.with_retry(_do, conn=self._get_connection())

    def get_report(
        self, report_id: int, user_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """根据 id 获取报告。若传入 user_id，则仅当该报告属于该用户时返回。"""
        conn = self._get_connection()
        cursor = conn.cursor()
        if user_id is not None:
            cursor.execute(
                "SELECT * FROM reports WHERE id = ? AND user_id = ?",
                (report_id, user_id),
            )
        else:
            cursor.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    def list_reports(
        self, user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """列出报告。若传入 user_id，仅返回该用户的报告；不传则返回全部。"""
        conn = self._get_connection()
        cursor = conn.cursor()
        if user_id is not None:
            cursor.execute(
                "SELECT * FROM reports WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
        else:
            cursor.execute("SELECT * FROM reports ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_report(
        self, report_id: int, user_id: Optional[int] = None, **kwargs
    ) -> bool:
        """更新报告。若传入 user_id，则仅当该报告属于该用户时才更新。"""
        allowed = {
            "name", "paper_ids", "paper_count", "status",
            "html_path", "pdf_path",
        }
        updates = []
        values = []
        for field, value in kwargs.items():
            if field not in allowed:
                continue
            if field == "paper_ids" and value is not None:
                value = json.dumps(value) if not isinstance(value, str) else value
            updates.append(f"{field} = ?")
            values.append(value)

        if not updates:
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(report_id)
        if user_id is not None:
            values.append(user_id)

        where_clause = "id = ? AND user_id = ?" if user_id is not None else "id = ?"

        def _do(cur):
            cur.execute(
                f"UPDATE reports SET {', '.join(updates)} WHERE {where_clause}",
                values,
            )
            return cur.rowcount > 0

        return BaseModel.with_retry(_do, conn=self._get_connection())

    def delete_report(
        self, report_id: int, user_id: Optional[int] = None
    ) -> bool:
        """删除报告。若传入 user_id，则仅当该报告属于该用户时才删除。"""
        def _do(cur):
            if user_id is not None:
                cur.execute(
                    "DELETE FROM reports WHERE id = ? AND user_id = ?",
                    (report_id, user_id),
                )
            else:
                cur.execute("DELETE FROM reports WHERE id = ?", (report_id,))
            return cur.rowcount > 0

        return BaseModel.with_retry(_do, conn=self._get_connection())
