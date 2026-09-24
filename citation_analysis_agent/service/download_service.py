"""
引文下载与服务层：从 API 查询引文、落库、下载 PDF；支持上传 PDF、查询某论文全部引文。
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Tuple

import requests

from model.model import DatabaseModel
from model.citation_model import CitationModel
from download.download_from_serp import (
    fetch_all_citations,
    search_article_and_get_citation_api,
)

# 默认存储根目录，与 serp_download_tools 一致
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


def _authors_from_api(item: Dict[str, Any]) -> List[str]:
    pub = item.get("publication_info") or {}
    authors = pub.get("authors") or []
    return [a.get("name") or "" for a in authors if isinstance(a, dict)]


def _year_from_summary(summary: Optional[str]) -> Optional[int]:
    if not summary:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", summary)
    return int(match.group(0)) if match else None


def _pdf_link_from_item(item: Dict[str, Any]) -> Optional[str]:
    resources = item.get("resources") or []
    for r in resources:
        if isinstance(r, dict) and r.get("link"):
            return r["link"]
    return None


def _cite_by_total_from_item(item: Dict[str, Any]) -> Optional[int]:
    inline = item.get("inline_links") or {}
    cited = inline.get("cited_by")
    if not isinstance(cited, dict):
        return None
    t = cited.get("total")
    return int(t) if t is not None else None

def _extract_venue_from_summary(summary: str) -> Optional[str]:
    """从 summary 中提取 venue，如 '...2025 - openreview.net' -> openreview"""
    if not summary or not isinstance(summary, str):
        return None
    parts = summary.split(" - ")
    if not parts:
        return None
    last = parts[-1].strip()
    if not last:
        return None
    # 取最后一个片段中域名部分（去掉 .net/.org/.com 等）
    venue_match = re.match(r"^([^.]+)", last)
    return venue_match.group(1) if venue_match else None
def _map_api_item_to_citation(paper_id: int, citation_id: int, item: Dict[str, Any]) -> Dict[str, Any]:
    pub = item.get("publication_info") or {}
    summary = pub.get("summary")
    return {
        "paper_id": paper_id,
        "citation_id": citation_id,
        "title": item.get("title"),
        "result_id": item.get("result_id"),
        "year": _year_from_summary(summary),
        "venue": _extract_venue_from_summary(summary),
        "summary": summary,
        "authors": _authors_from_api(item) or None,
        "download_status": None,
        "download_error": None,
        "analysis_status": None,
        "download_link": _pdf_link_from_item(item),
        "cite_by_total": _cite_by_total_from_item(item),
        "path": None,
    }


def _download_pdf(url: str, save_path: str) -> tuple[str, Optional[str]]:
    """尝试下载 PDF 到 save_path。返回 (status, error)。"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        if not resp.content.startswith(b"%PDF"):
            return "failed", "content is not PDF"
        with open(save_path, "wb") as f:
            f.write(resp.content)
        return "success", None
    except Exception as e:
        return "failed", str(e)


def _write_result_json(
    citations_dir: str,
    raw_items: List[Dict[str, Any]],
    citations_by_id: Dict[int, Dict[str, Any]],
) -> str:
    """
    将 fetch_all_citations 的原始引文信息写出为 result.json，仅补充 id 和 download 字段。
    保证 result.json 保存的是下载时 fetch_all_citations 获取到的所有引文原信息。
    raw_items: 原始 API 返回的引文列表（含 position, link, snippet, resources, inline_links 等）
    citations_by_id: citation_id -> 数据库中的引文记录（用于 merge download 状态）
    """
    result = []
    for idx, raw in enumerate(raw_items, start=1):
        item = dict(raw)  # 保留全部原信息
        item["id"] = idx
        db_row = citations_by_id.get(idx, {})
        item["download"] = {
            "status": db_row.get("download_status") or "skipped",
            "pdf_path": db_row.get("path"),
            "error": db_row.get("download_error"),
        }
        result.append(item)
    path = os.path.join(citations_dir, "result.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return path


def _download_one(
    task: Tuple[int, str, str],
) -> Tuple[int, str, Optional[str], Optional[str]]:
    """单任务下载，供线程池调用。返回 (citation_id, status, error, abs_path)。"""
    citation_id, pdf_url, pdf_path = task
    status, err = _download_pdf(pdf_url, pdf_path)
    abs_path = os.path.normpath(os.path.abspath(pdf_path)) if status == "success" else None
    return (citation_id, status, err, abs_path)


# -----------------------------------------------------------------------------
# 1. 给一个 paper_id，查询并下载其所有引文（落库 + 更新）
# -----------------------------------------------------------------------------


def download_all_citations_for_paper(
    paper_id: int,
    *,
    storage_root: str = DEFAULT_STORAGE_ROOT,
    cite_url: Optional[str] = None,
    max_citations: int = 500,
    max_workers: int = 8,
) -> Dict[str, Any]:
    """
    根据 paper_id 查询该论文的引文 API，拉取引文列表，写入 citations 表，并并行下载 PDF。
    若未传 cite_url，则从 papers 表取 cite_link；若没有则按论文 title 搜索得到引用 API。
    max_workers: 并行下载 PDF 的线程数，默认 8。

    Returns:
        {
            "paper_id": int,
            "count": int,           # 本批新增/更新的引文数
            "downloaded": int,      # PDF 成功下载数
            "failed": int,
            "skipped": int,
            "citations": [ ... ]    # 本论文下全部引文（DB 查询结果）
        }
    """
    db = DatabaseModel()
    cm = CitationModel()
    paper = db.get_paper(paper_id)
    if not paper:
        raise ValueError(f"paper_id={paper_id} not found")

    print("cite_url:", cite_url)
    url = cite_url or paper.get("cite_link")
    print("url:", url)
    if not url:
        print("no url, search article and get citation api")
        info = search_article_and_get_citation_api(paper["title"])
        if not info:
            raise ValueError(f"no citation API for paper '{paper['title']}'")
        url = info["citation_api"]
        
    print("url:", url)

    raw = fetch_all_citations(url, max_len=max_citations)
    raw = raw[:max_citations]
    if not raw:
        db.update_paper(paper_id, analysis_status="DOWNLOADED")
        return {
            "paper_id": paper_id,
            "count": 0,
            "downloaded": 0,
            "failed": 0,
            "skipped": 0,
            "citations": [],
        }

    db.update_paper(paper_id, analysis_status="DOWNLOADING")
    citations_dir = _build_citations_dir(storage_root, paper_id)

    # 先删除该论文下已有引文（本次视为全量覆盖）
    cm.delete_citations_by_paper(paper_id)

    downloaded = 0
    failed = 0
    skipped = 0

    # 1) 落库所有引文元数据
    download_tasks: List[Tuple[int, str, str]] = []  # (citation_id, pdf_url, pdf_path)
    for idx, item in enumerate(raw, start=1):
        meta = _map_api_item_to_citation(paper_id, idx, item)
        cm.add_citation(
            paper_id=paper_id,
            citation_id=idx,
            title=meta["title"],
            result_id=meta["result_id"],
            year=meta["year"],
            venue=meta["venue"],
            summary=meta["summary"],
            authors=meta["authors"],
            download_link=meta["download_link"],
            cite_by_total=meta["cite_by_total"],
        )
        pdf_path = os.path.join(citations_dir, f"Citation_{idx}.pdf")
        pdf_url = meta["download_link"]

        if not pdf_url:
            cm.update_citation(
                paper_id, idx,
                download_status="skipped",
                download_error="no pdf link",
                path=None,
            )
            skipped += 1
            continue

        if os.path.exists(pdf_path):
            abs_path = os.path.normpath(os.path.abspath(pdf_path))
            cm.update_citation(
                paper_id, idx,
                download_status="exists",
                download_error=None,
                path=abs_path,
            )
            skipped += 1
            continue

        download_tasks.append((idx, pdf_url, pdf_path))

    # 2) 多线程并行下载
    workers = min(max_workers, len(download_tasks), 16)
    if download_tasks and workers > 0:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_download_one, t): t[0] for t in download_tasks}
            for future in as_completed(futures):
                try:
                    citation_id, status, err, abs_path = future.result()
                    cm.update_citation(
                        paper_id, citation_id,
                        download_status=status,
                        download_error=err,
                        path=abs_path,
                    )
                    if status == "success":
                        downloaded += 1
                    else:
                        failed += 1
                except Exception as e:
                    citation_id = futures[future]
                    cm.update_citation(
                        paper_id, citation_id,
                        download_status="failed",
                        download_error=str(e),
                        path=None,
                    )
                    failed += 1

    db.update_paper(paper_id, analysis_status="DOWNLOADED")
    citations = cm.get_citations_by_paper(paper_id)

    # 若 paper.citation_number 为 -1（默认值），用查询到的引文数量更新
    if paper.get("citation_number") == -1:
        db.update_paper(paper_id, citation_number=len(citations))

    # 保存原始 API 数据到 raw_citations.json（备份）
    raw_path = os.path.join(citations_dir, "raw_citations.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)

    # 写出 result.json：原信息 + id + download 状态
    citations_by_id = {c["citation_id"]: c for c in citations}
    _write_result_json(citations_dir, raw, citations_by_id)

    return {
        "paper_id": paper_id,
        "count": len(citations),
        "downloaded": downloaded,
        "failed": failed,
        "skipped": skipped,
        "citations": citations,
    }


# -----------------------------------------------------------------------------
# 2. 给 paper_id、citation_id 和 PDF 文件，上传该引文的 PDF
# -----------------------------------------------------------------------------


def upload_citation_pdf(
    paper_id: int,
    citation_id: int,
    pdf_file: Any,
    *,
    storage_root: str = DEFAULT_STORAGE_ROOT,
) -> Dict[str, Any]:
    """
    上传某条引文的 PDF。pdf_file 需有 .read() 与 .filename（如 Werkzeug FileStorage）。
    会覆盖已存在的 Citation_{citation_id}.pdf。

    Returns:
        {
            "paper_id": int,
            "citation_id": int,
            "path": str,
            "success": bool,
        }
    """
    cm = CitationModel()
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

    return {
        "paper_id": paper_id,
        "citation_id": citation_id,
        "path": abs_path,
        "success": True,
    }


# -----------------------------------------------------------------------------
# 3. 查询某个 paper 的所有引文信息（从 DB）
# -----------------------------------------------------------------------------


def get_citations_for_paper(paper_id: int) -> List[Dict[str, Any]]:
    """
    查询某篇论文的全部引文，按 citation_id 升序。数据来自 citations 表。
    """
    cm = CitationModel()
    return cm.get_citations_by_paper(paper_id)

if __name__ == "__main__":
    result=fetch_all_citations("https://serpapi.com/search.json?as_sdt=5%2C39&cites=7786355174955884281&engine=google_scholar&hl=en")
    print(result)