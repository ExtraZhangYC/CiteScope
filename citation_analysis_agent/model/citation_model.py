"""
SQLite 数据库模型：管理论文的引文信息
- 表 citations：(paper_id, citation_id) 联合主键，citation_id 按论文单独累计
- 引文补充字段均可选，支持更新
"""

import sqlite3
import json
from typing import Optional, List, Dict, Any

from model.base import BaseModel


class CitationModel(BaseModel):
    """引文模型类，提供 citations 表的 CRUD 接口"""

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
        conn = super()._get_conn()
        return conn

    def _init_database(self):
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS citations (
                paper_id INTEGER NOT NULL,
                citation_id INTEGER NOT NULL,
                title TEXT,
                result_id TEXT,
                year INTEGER,
                venue TEXT,
                summary TEXT,
                authors TEXT,
                download_status TEXT,
                download_error TEXT,
                analysis_status TEXT,
                download_link TEXT,
                cite_by_total INTEGER,
                path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (paper_id, citation_id),
                FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
            )
        """)

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_citations_paper_id ON citations(paper_id)"
        )

        conn.commit()

    def close(self):
        # 兼容旧 API。BaseModel 单例模式下不做任何操作。
        pass

    # ==================== 辅助 ====================

    def _row_to_dict(self, row) -> Dict[str, Any]:
        data = dict(row)
        if data.get("authors") is not None:
            try:
                data["authors"] = json.loads(data["authors"])
            except (json.JSONDecodeError, TypeError):
                pass
        return data

    def _next_citation_id(self, paper_id: int) -> int:
        """返回该论文下可用的下一个 citation_id（从 1 起按篇累计）"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COALESCE(MAX(citation_id), 0) + 1 AS next FROM citations WHERE paper_id = ?",
            (paper_id,),
        )
        row = cursor.fetchone()
        return row["next"] if row else 1

    # ==================== 增删改查 ====================

    def add_citation(
        self,
        paper_id: int,
        citation_id: Optional[int] = None,
        title: Optional[str] = None,
        result_id: Optional[str] = None,
        year: Optional[int] = None,
        venue: Optional[str] = None,
        summary: Optional[str] = None,
        authors: Optional[List[str]] = None,
        download_status: Optional[str] = None,
        download_error: Optional[str] = None,
        analysis_status: Optional[str] = None,
        download_link: Optional[str] = None,
        cite_by_total: Optional[int] = None,
        path: Optional[str] = None,
    ) -> int:
        """
        添加一条引文。若未传 citation_id，则自动分配该 paper 下的下一个编号（1,2,3...）。
        """
        cid = citation_id
        if cid is None:
            cid = self._next_citation_id(paper_id)

        authors_json = json.dumps(authors) if authors is not None else None

        def _do(cur):
            cur.execute("""
                INSERT INTO citations
                (paper_id, citation_id, title, result_id, year, venue, summary,
                 authors, download_status, download_error, analysis_status,
                 download_link, cite_by_total, path, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                paper_id,
                cid,
                title,
                result_id,
                year,
                venue,
                summary,
                authors_json,
                download_status,
                download_error,
                analysis_status,
                download_link,
                cite_by_total,
                path,
            ))
            return cid

        return BaseModel.with_retry(_do, conn=self._get_connection())

    def get_citation(
        self, paper_id: int, citation_id: int
    ) -> Optional[Dict[str, Any]]:
        """根据 (paper_id, citation_id) 获取一条引文"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM citations WHERE paper_id = ? AND citation_id = ?",
            (paper_id, citation_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_dict(row)

    def get_citations_by_paper(
        self, paper_id: int
    ) -> List[Dict[str, Any]]:
        """获取某篇论文下的全部引文，按 citation_id 升序"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM citations WHERE paper_id = ? ORDER BY citation_id ASC",
            (paper_id,),
        )
        rows = cursor.fetchall()
        return [self._row_to_dict(r) for r in rows]

    def update_citation(
        self, paper_id: int, citation_id: int, **kwargs
    ) -> bool:
        """
        更新引文补充信息，仅更新传入的字段。可传 None 以清空某字段。
        允许的字段：title, result_id, year, venue, summary, authors,
        download_status, download_error, analysis_status, download_link,
        cite_by_total, path.
        """
        allowed = {
            "title", "result_id", "year", "venue", "summary", "authors",
            "download_status", "download_error", "analysis_status",
            "download_link", "cite_by_total", "path",
        }
        updates = []
        values = []

        for k, v in kwargs.items():
            if k not in allowed:
                continue
            val = json.dumps(v) if k == "authors" else v
            updates.append(f"{k} = ?")
            values.append(val)

        if not updates:
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.extend([paper_id, citation_id])

        def _do(cur):
            cur.execute(
                f"UPDATE citations SET {', '.join(updates)} WHERE paper_id = ? AND citation_id = ?",
                values,
            )
            return cur.rowcount > 0

        return BaseModel.with_retry(_do, conn=self._get_connection())

    def delete_citation(self, paper_id: int, citation_id: int) -> bool:
        """删除一条引文"""
        def _do(cur):
            cur.execute(
                "DELETE FROM citations WHERE paper_id = ? AND citation_id = ?",
                (paper_id, citation_id),
            )
            return cur.rowcount > 0

        return BaseModel.with_retry(_do, conn=self._get_connection())

    def delete_citations_by_paper(self, paper_id: int) -> int:
        """删除某篇论文下的全部引文，返回删除条数"""
        def _do(cur):
            cur.execute("DELETE FROM citations WHERE paper_id = ?", (paper_id,))
            return cur.rowcount

        return BaseModel.with_retry(_do, conn=self._get_connection())

    def count_by_paper(self, paper_id: int) -> int:
        """某篇论文下的引文数量"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) AS n FROM citations WHERE paper_id = ?",
            (paper_id,),
        )
        row = cursor.fetchone()
        return row["n"] if row else 0

    def get_counts_by_paper(self, paper_id: int) -> Dict[str, int]:
        """
        某篇论文下的引文统计：总数、下载成功数、分析成功数。
        下载成功：download_status IN ('success','exists')
        分析成功：analysis_status IN ('analysised','completed','success')
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) AS n FROM citations WHERE paper_id = ?",
            (paper_id,),
        )
        total = cursor.fetchone()["n"] or 0
        cursor.execute(
            """SELECT COUNT(*) AS n FROM citations WHERE paper_id = ?
               AND download_status IN ('success','exists')""",
            (paper_id,),
        )
        downloaded = cursor.fetchone()["n"] or 0
        cursor.execute(
            """SELECT COUNT(*) AS n FROM citations WHERE paper_id = ?
               AND analysis_status IN ('analysised','completed','success')""",
            (paper_id,),
        )
        analyzed = cursor.fetchone()["n"] or 0
        return {
            "citation_count": total,
            "downloaded_count": downloaded,
            "analyzed_count": analyzed,
        }
