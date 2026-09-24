"""
分析服务层：多线程引文分析，从数据库读取引文信息，分析完成后更新 analysis_status。
报告仍写入文件：multiprocess_analysis_report.json、summarize_report.json
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

from agent.workflows import run_minimal_analysis, run_supervisor_analysis, run_summarize
from service.citations_service import (
    get_citations_for_paper,
    get_downloaded_citation_ids,
    update_citation_status,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _paper_id_from_citations_path(path: str) -> Optional[int]:
    """
    从 citations 目录路径提取 paper_id。
    如 storage/papers/62/citations -> 62
    """
    path_norm = path.replace("\\", "/")
    m = re.search(r"papers/(\d+)/citations", path_norm)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return None


def process_citation(
    citations_dir: str,
    citation_id: int,
    mode: str,
    paper_id: Optional[int] = None,
) -> list:
    """
    处理单个 citation 的分析任务。
    citations_dir: 目录路径，供 agent 读取 PDF
    paper_id: DB 中的 paper_id，用于更新 analysis_status
    """
    try:
        if mode == "minimal":
            result = run_minimal_analysis(
                paper_id=citations_dir,
                citation_ids=[citation_id],
                write_output=False,
            )
        elif mode == "agentic":
            result = run_supervisor_analysis(
                paper_id=citations_dir,
                citation_ids=[citation_id],
                write_output=False,
            )
        else:
            raise ValueError(f"不支持的分析模式: {mode}")

        if result and paper_id is not None:
            update_citation_status(
                paper_id,
                citation_id,
                analysis_status="analysised",
            )
        return result
    except Exception as exc:
        logger.exception("process_citation failed: %s", exc)
        return []


def run_multithread_service(
    citations_dir: str,
    paper_id: Optional[int] = None,
    mode: str = "minimal",
    max_workers: int = 3,
) -> list:
    """
    运行多线程分析：从数据库读取引文列表，分析完成后更新 citations.analysis_status。
    报告写入 multiprocess_analysis_report.json。

    Args:
        citations_dir: citations 目录路径（如 storage/papers/62/citations）
        paper_id: DB 中的 paper_id，用于查询和更新。若为 None 则从路径解析
        mode: 分析模式（minimal/agentic）
        max_workers: 最大线程数。SQLite 是文件级写锁，过高的并发只会
                     制造 ``database is locked`` 争抢；分析本身是 IO 密集，
                     默认 3 已足够。

    Returns:
        所有处理结果的列表
    """
    pid = paper_id if paper_id is not None else _paper_id_from_citations_path(citations_dir)
    if pid is None:
        raise ValueError(f"无法从路径解析 paper_id: {citations_dir}")

    all_results: list = []
    output_path = Path(citations_dir) / "multiprocess_analysis_report.json"

    def save_results():
        sorted_results = sorted(all_results, key=lambda x: int(x["id"]))
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(sorted_results, f, ensure_ascii=False, indent=2)

    # 从数据库获取引文
    citation_data = get_citations_for_paper(pid)
    citations_by_id = {c.get("citation_id") or c.get("id"): c for c in citation_data}
    all_citation_ids = sorted(citations_by_id.keys())
    downloaded_citation_ids = get_downloaded_citation_ids(pid)

    def get_title(cid: int) -> str:
        c = citations_by_id.get(cid, {})
        return c.get("title") or ""

    # 跳过已分析过的
    finished_citation_ids: List[int] = []
    if output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            all_results = list(existing)
            finished_citation_ids = sorted(
                int(item["id"])
                for item in existing
                if item.get("status") == "analysised"
            )
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_citation = {}
        for citation_id in all_citation_ids:
            if (
                citation_id is None
                or citation_id in finished_citation_ids
                or citation_id not in downloaded_citation_ids
            ):
                continue
            future = executor.submit(
                process_citation,
                citations_dir,
                citation_id,
                mode,
                pid,
            )
            future_to_citation[future] = citation_id

        for future in as_completed(future_to_citation):
            citation_id = future_to_citation[future]
            try:
                result = future.result()
                if result:
                    result[0]["status"] = "analysised"
                    all_results.extend(result)
                else:
                    all_results.append({
                        "id": citation_id,
                        "paper": get_title(citation_id),
                        "citations": [],
                        "status": "downloaded",
                        "error": "empty result",
                    })
                save_results()
            except Exception as exc:
                all_results.append({
                    "id": citation_id,
                    "paper": get_title(citation_id),
                    "citations": [],
                    "status": "downloaded",
                    "error": str(exc),
                })
                save_results()

    for cid in all_citation_ids:
        if cid not in [int(item["id"]) for item in all_results]:
            all_results.append({
                "id": cid,
                "paper": get_title(cid),
                "citations": [],
                "status": "not_downloaded",
            })
    all_results = sorted(all_results, key=lambda x: int(x["id"]))

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    return all_results


def run_single_citation_analysis(
    citations_dir: str,
    citation_id: int,
    paper_id: Optional[int] = None,
    mode: str = "minimal",
) -> list:
    """
    针对单个 citation 执行分析，增量写入 multiprocess_analysis_report.json。
    分析成功后更新 citations.analysis_status。
    """
    pid = paper_id if paper_id is not None else _paper_id_from_citations_path(citations_dir)
    if pid is None:
        raise ValueError(f"无法从路径解析 paper_id: {citations_dir}")

    output_path = Path(citations_dir) / "multiprocess_analysis_report.json"
    citation_data = get_citations_for_paper(pid)
    citations_by_id = {c.get("citation_id") or c.get("id"): c for c in citation_data}

    def get_title(cid: int) -> str:
        c = citations_by_id.get(cid, {})
        return c.get("title") or ""

    all_results: list = []
    if output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                all_results = json.load(f)
        except Exception:
            pass

    all_results = [item for item in all_results if int(item.get("id", -1)) != int(citation_id)]

    downloaded_citation_ids = get_downloaded_citation_ids(pid)
    if citation_id not in downloaded_citation_ids:
        all_results.append({
            "id": int(citation_id),
            "paper": get_title(citation_id),
            "citations": [],
            "status": "not_downloaded",
        })
        all_results = sorted(all_results, key=lambda x: int(x["id"]))
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        return all_results

    try:
        result = process_citation(citations_dir, citation_id, mode, pid)
        if result:
            result[0]["status"] = "analysised"
            all_results.extend(result)
        else:
            all_results.append({
                "id": int(citation_id),
                "paper": get_title(citation_id),
                "citations": [],
                "status": "downloaded",
                "error": "empty result",
            })
    except Exception as exc:
        all_results.append({
            "id": int(citation_id),
            "paper": get_title(citation_id),
            "citations": [],
            "status": "downloaded",
            "error": str(exc),
        })

    all_results = sorted(all_results, key=lambda x: int(x["id"]))
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    return all_results


def run_summarize_analysis(citations_dir: str, paper_id: Optional[int] = None) -> list:
    """
    对 multiprocess_analysis_report.json 中的结果进行总结，
    写入 summarize_report.json。
    """
    report_path = Path(citations_dir) / "multiprocess_analysis_report.json"
    output_path = Path(citations_dir) / "summarize_report.json"

    all_results: list = []
    if report_path.exists():
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                all_results = json.load(f)
        except Exception:
            pass

    summation = run_summarize(all_results)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summation, f, ensure_ascii=False, indent=2)
    return summation
