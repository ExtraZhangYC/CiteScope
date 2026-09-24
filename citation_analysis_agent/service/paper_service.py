"""
论文服务层：论文 CRUD、引文统计、信息提取等。
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional, List, Dict, Any

from model.model import DatabaseModel
from model.citation_model import CitationModel

DEFAULT_STORAGE_ROOT = "storage"


def _write_paper_info_json(paper_id: int, data: Dict[str, Any], storage_root: str = DEFAULT_STORAGE_ROOT) -> str:
    """
    在论文保存目录下写入 info.json。
    格式: ScholarID, ApproachName, Title, Authors, Venue, Year
    """
    paper_dir = os.path.join(storage_root, "papers", str(paper_id),"citations")
    os.makedirs(paper_dir, exist_ok=True)
    path = os.path.join(paper_dir, "info.json")
    approach = data.get("approach_name") or []
    if isinstance(approach, str):
        try:
            approach = json.loads(approach) if approach else []
        except (json.JSONDecodeError, TypeError):
            approach = []
    authors = data.get("authors") or []
    if isinstance(authors, str):
        try:
            authors = json.loads(authors) if authors else []
        except (json.JSONDecodeError, TypeError):
            authors = []
    year_val = data.get("year")
    year_str = str(year_val) if year_val is not None else ""
    info = {
        "ScholarID": "",
        "ApproachName": approach,
        "Title": data.get("title") or "",
        "Authors": authors,
        "Venue": data.get("venue") or "",
        "Year": year_str,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    return path


def _extract_year_from_summary(summary: str) -> Optional[int]:
    """从 summary 中提取年份，如 '...2025 - openreview.net' -> 2025"""
    if not summary or not isinstance(summary, str):
        return None
    match = re.search(r"\b(19|20)\d{2}\b", summary)
    return int(match.group(0)) if match else None


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


def _extract_approach_name_from_title(title: str) -> Optional[List[str]]:
    """从 title 中提取 approach_name，如 'FAN:Fourier Analysis Network' -> ['FAN']"""
    if not title or not isinstance(title, str) or ":" not in title:
        return None
    before_colon = title.split(":")[0].strip()
    if not before_colon:
        return None
    return [before_colon]


def enrich_paper_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据 summary、title 完善 year、venue、approach_name。
    仅当能提取到且对应字段未提供时才填充，不覆盖已有值。
    """
    result = dict(data)
    summary = result.get("summary")
    title = result.get("title")

    if summary:
        if result.get("year") is None:
            year = _extract_year_from_summary(summary)
            if year is not None:
                result["year"] = year
        if result.get("venue") is None or result.get("venue") == "":
            venue = _extract_venue_from_summary(summary)
            if venue is not None:
                result["venue"] = venue

    if title and (result.get("approach_name") is None or result.get("approach_name") == []):
        approach = _extract_approach_name_from_title(title)
        if approach is not None:
            result["approach_name"] = approach

    return result


def _attach_citation_counts(paper: Dict[str, Any], cm: CitationModel) -> None:
    """给 paper 字典附加引文统计字段。"""
    paper_id = paper.get("id")
    if paper_id is None:
        return
    counts = cm.get_counts_by_paper(paper_id)
    paper["citation_count"] = counts["citation_count"]
    paper["downloaded_count"] = counts["downloaded_count"]
    paper["analyzed_count"] = counts["analyzed_count"]
    paper["not_downloaded_count"] = counts["citation_count"] - counts["downloaded_count"]


# -----------------------------------------------------------------------------
# 查询论文（带引文统计）
# -----------------------------------------------------------------------------


def get_paper(
    paper_id: int,
    *,
    user_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    根据 id 获取论文，并附加引文统计（citation_count, downloaded_count, analyzed_count）。
    """
    db = DatabaseModel()
    cm = CitationModel()
    paper = db.get_paper(paper_id, user_id=user_id)
    if not paper:
        return None
    _attach_citation_counts(paper, cm)
    return paper


def list_papers(
    *,
    user_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    列出论文，每条附加引文统计。
    """
    db = DatabaseModel()
    cm = CitationModel()
    papers = db.list_papers(user_id=user_id)
    for p in papers:
        _attach_citation_counts(p, cm)
    return papers


# -----------------------------------------------------------------------------
# 增删改
# -----------------------------------------------------------------------------


def add_paper(user_id: int, **kwargs) -> int:
    """添加论文，根据 summary/title 自动完善 year、venue、approach_name，写入 info.json，返回 paper_id。"""
    db = DatabaseModel()
    kwargs["user_id"] = user_id
    enriched = enrich_paper_data(kwargs)
    paper_id = db.add_paper(**enriched)
    _write_paper_info_json(paper_id, enriched)
    return paper_id


def update_paper(
    paper_id: int,
    *,
    user_id: Optional[int] = None,
    **kwargs,
) -> bool:
    """更新论文。"""
    db = DatabaseModel()
    return db.update_paper(paper_id, user_id=user_id, **kwargs)


def delete_paper(
    paper_id: int,
    *,
    user_id: Optional[int] = None,
) -> bool:
    """删除论文。"""
    db = DatabaseModel()
    return db.delete_paper(paper_id, user_id=user_id)
