"""
引文服务层：查询引文、更新下载/分析状态、上传 PDF 等。
基于 citation_model，面向 citations 表的业务封装。
"""

from __future__ import annotations

import json
import os
from typing import List, Dict, Any, Optional

from model.citation_model import CitationModel
from model.model import DatabaseModel

DEFAULT_STORAGE_ROOT = "storage"


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _build_citations_dir(storage_root: str, paper_id: int) -> str:
    """storage/papers/{paper_id}/citations/"""
    root = os.path.join(storage_root, "papers", str(paper_id))
    citations_dir = os.path.join(root, "citations")
    _ensure_dir(root)
    _ensure_dir(citations_dir)
    return citations_dir


def _write_result_json(citations_dir: str, citations: List[Dict[str, Any]]) -> str:
    """
    同步 result.json。优先从 raw_citations.json 读取原信息并合并 DB 的 download 状态；
    若不存在 raw，则从 citations（DB）构建简化格式供分析服务兼容。
    """
    path = os.path.join(citations_dir, "result.json")
    raw_path = os.path.join(citations_dir, "raw_citations.json")
    citations_by_id = {c.get("citation_id") or c.get("id"): c for c in citations}

    # 有 raw_citations.json 时，保留原信息并合并 download
    if os.path.exists(raw_path):
        try:
            with open(raw_path, "r", encoding="utf-8") as f:
                raw_items = json.load(f)
            result = []
            for idx, raw in enumerate(raw_items, start=1):
                item = dict(raw)
                item["id"] = idx
                db_row = citations_by_id.get(idx, {})
                item["download"] = {
                    "status": db_row.get("download_status") or "skipped",
                    "pdf_path": db_row.get("path"),
                    "error": db_row.get("download_error"),
                }
                result.append(item)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            return path
        except Exception:
            pass

    # 无 raw 时，从 DB 构建简化格式
    result = []
    for c in citations:
        authors = c.get("authors") or []
        authors_data = [{"name": a} if isinstance(a, str) else a for a in authors]
        result.append({
            "id": c.get("citation_id") or c.get("id"),
            "title": c.get("title", ""),
            "publication_info": {
                "summary": c.get("summary", ""),
                "authors": authors_data,
            },
            "download": {
                "status": c.get("download_status") or "skipped",
                "pdf_path": c.get("path"),
                "error": c.get("download_error"),
            },
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return path


# -----------------------------------------------------------------------------
# 1. 查询某篇 paper 的所有引文
# -----------------------------------------------------------------------------


def get_citations_for_paper(
    paper_id: int,
    *,
    user_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    查询某篇论文的全部引文，按 citation_id 升序。
    返回 citations 表全部字段，并附带 id、download 等兼容字段。
    若传入 user_id，则先校验该 paper 属于该用户。
    """
    db = DatabaseModel()
    cm = CitationModel()
    if user_id is not None:
        paper = db.get_paper(paper_id, user_id=user_id)
        if not paper:
            raise ValueError(f"paper_id={paper_id} not found or access denied")
    rows = cm.get_citations_by_paper(paper_id)
    # 确保返回完整字段，并增加 id、download、publication_info 等兼容结构
    result = []
    for c in rows:
        item = dict(c)
        item["id"] = item.get("citation_id")
        # item["download"] = {
        #     "status": item.get("download_status") or "skipped",
        #     "pdf_path": item.get("path"),
        #     "error": item.get("download_error"),
        # }
        # authors = item.get("authors") or []
        # authors_data = [{"name": a} if isinstance(a, str) else a for a in authors]
        # item["publication_info"] = {
        #     "summary": item.get("summary", ""),
        #     "authors": authors_data,
        # }
        result.append(item)
    return result


# -----------------------------------------------------------------------------
# 1.5 获取已下载的引文 ID 列表（供分析服务使用）
# -----------------------------------------------------------------------------


def get_downloaded_citation_ids(paper_id: int) -> List[int]:
    """
    返回某论文下已下载 PDF 的 citation_id 列表。
    下载成功：download_status IN ('success','exists')
    """
    cm = CitationModel()
    rows = cm.get_citations_by_paper(paper_id)
    return sorted(
        c.get("citation_id") or c.get("id")
        for c in rows
        if c.get("citation_id") is not None
        and c.get("download_status") in ("success", "exists")
    )


# -----------------------------------------------------------------------------
# 2. 更新引文的下载/分析状态
# -----------------------------------------------------------------------------


def update_citation_status(
    paper_id: int,
    citation_id: int,
    *,
    download_status: Optional[str] = None,
    analysis_status: Optional[str] = None,
    download_error: Optional[str] = None,
    user_id: Optional[int] = None,
) -> bool:
    """
    更新某条引文的下载状态和/或分析状态。
    """
    db = DatabaseModel()
    cm = CitationModel()
    if user_id is not None:
        paper = db.get_paper(paper_id, user_id=user_id)
        if not paper:
            raise ValueError(f"paper_id={paper_id} not found or access denied")
    cit = cm.get_citation(paper_id, citation_id)
    if not cit:
        raise ValueError(f"citation (paper_id={paper_id}, citation_id={citation_id}) not found")
    kwargs = {}
    if download_status is not None:
        kwargs["download_status"] = download_status
    if analysis_status is not None:
        kwargs["analysis_status"] = analysis_status
    if download_error is not None:
        kwargs["download_error"] = download_error
    if not kwargs:
        return False
    return cm.update_citation(paper_id, citation_id, **kwargs)


# -----------------------------------------------------------------------------
# 3. 上传 PDF 并更新引文状态为已下载
# -----------------------------------------------------------------------------


def upload_citation_pdf(
    paper_id: int,
    citation_id: int,
    pdf_file: Any,
    *,
    storage_root: str = DEFAULT_STORAGE_ROOT,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    上传某条引文的 PDF，保存到 storage，并更新 citations 表：
    download_status="success", download_error=None, path=保存路径。
    同时同步 result.json 供分析服务兼容。
    """
    db = DatabaseModel()
    cm = CitationModel()
    if user_id is not None:
        paper = db.get_paper(paper_id, user_id=user_id)
        if not paper:
            raise ValueError(f"paper_id={paper_id} not found or access denied")
    cit = cm.get_citation(paper_id, citation_id)
    if not cit:
        raise ValueError(f"citation (paper_id={paper_id}, citation_id={citation_id}) not found")

    citations_dir = _build_citations_dir(storage_root, paper_id)
    filename = f"Citation_{citation_id}.pdf"
    save_path = os.path.join(citations_dir, filename)

    if hasattr(pdf_file, "seek"):
        pdf_file.seek(0)
    data = pdf_file.read() if hasattr(pdf_file, "read") else pdf_file
    if isinstance(data, str):
        data = data.encode()
    with open(save_path, "wb") as f:
        f.write(data)

    abs_path = os.path.normpath(os.path.abspath(save_path))
    cm.update_citation(
        paper_id, citation_id,
        download_status="success",
        download_error=None,
        path=abs_path,
    )

    # 同步 result.json
    citations = cm.get_citations_by_paper(paper_id)
    _write_result_json(citations_dir, citations)

    return {
        "paper_id": paper_id,
        "citation_id": citation_id,
        "path": abs_path,
        "success": True,
    }
