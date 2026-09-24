from flask import Blueprint, request, jsonify
import os
import json
import threading
from model.model import DatabaseModel
from service.analysis_service import (
    run_multithread_service,
    run_single_citation_analysis,
    run_summarize_analysis,
)
from service.citations_service import get_citations_for_paper
from utils.response import make_response
from utils.auth import token_required, get_current_user_id
from service.download_service import download_all_citations_for_paper

analysis_bp = Blueprint("analysis", __name__)
db_analysis = DatabaseModel()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STORAGE_DIR = os.path.join(BASE_DIR, "storage", "papers")


# ==================== 并发保护 ====================
# 同一 paper 同时只能有一个后台任务在跑。
# 这里使用进程内 threading.Lock；多 worker 部署时改用 Redis 即可。
_PAPER_LOCKS: dict = {}
_PAPER_LOCKS_META: threading.Lock = threading.Lock()

# 已声明"正在跑"的状态集合（同一状态再次点击视为重复）
_RUNNING_STATUSES = {"ANALYZING", "DOWNLOADING", "DOWNLOADED"}


def _get_paper_lock(paper_id: int) -> threading.Lock:
    with _PAPER_LOCKS_META:
        lock = _PAPER_LOCKS.get(paper_id)
        if lock is None:
            lock = threading.Lock()
            _PAPER_LOCKS[paper_id] = lock
        return lock


def _try_acquire_paper(paper_id: int) -> bool:
    """非阻塞获取该 paper 的运行锁。"""
    return _get_paper_lock(paper_id).acquire(blocking=False)


def _release_paper(paper_id: int) -> None:
    lock = _PAPER_LOCKS.get(paper_id)
    if lock and lock.locked():
        lock.release()


# ---------------------------------------------------------------------------

@analysis_bp.route("/analysis/<int:paper_id>", methods=["GET"])
@token_required
def get_analysis(paper_id):
    """
    获取论文分析，存储路径:
    storage/papers/{id}/citations/multiprocess_analysis_report.json
    """
    paper = db_analysis.get_paper(paper_id, user_id=get_current_user_id())
    if not paper:
        return make_response(False, 404, "paper not found", None)

    analysis_path = os.path.join(
        STORAGE_DIR,
        str(paper_id),
        "citations",
        "multiprocess_analysis_report.json"
    )

    if not os.path.exists(analysis_path):
        return make_response(
            success=False,
            code=404,
            message="analysis report not found,please check the paper status",
            data={"paper_id": paper_id}
        )

    try:
        with open(analysis_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return make_response(
            success=False,
            code=500,
            message="failed to read analysis file",
            data={"error": str(e)}
        )

    # 从数据库获取引文下载信息
    citations = get_citations_for_paper(paper_id, user_id=get_current_user_id())
    download_by_id = {
        c.get("citation_id") or c.get("id"): {
            "status": c.get("download_status") or "skipped",
            "pdf_path": c.get("path"),
            "error": c.get("download_error"),
        }
        for c in citations
    }

    data_inc = sorted(data, key=lambda x: x["id"])
    return make_response(
        success=True,
        code=200,
        message="analysis loaded successfully",
        data={
            "paper_id": paper_id,
            "analysis": data_inc
        }
    )


@analysis_bp.route("/analysis/<int:paper_id>", methods=["POST"])
@token_required
def start_analysis(paper_id: int):
    """
    异步启动论文分析任务
    """
    paper = db_analysis.get_paper(paper_id, user_id=get_current_user_id())
    if not paper:
        return make_response(False, 404, "paper not found", None)

    analysis_path = os.path.join(
        "storage", "papers", str(paper_id), "citations"
    )
    if not os.path.exists(analysis_path):
        return make_response(
            success=False,
            code=404,
            message="analysis report not found",
            data={"paper_id": paper_id})

    # 防止重复触发：已在跑就直接拒
    if not _try_acquire_paper(paper_id):
        return make_response(
            False, 409,
            "another analysis task is running for this paper",
            {"paper_id": paper_id, "status": paper.get("analysis_status")},
        )
    if (paper.get("analysis_status") or "").upper() in _RUNNING_STATUSES:
        _release_paper(paper_id)
        return make_response(
            False, 409,
            "analysis already in progress",
            {"paper_id": paper_id, "status": paper.get("analysis_status")},
        )

    uid = get_current_user_id()

    def background_task():
        try:
            db_analysis.update_paper(paper_id, user_id=uid, analysis_status="ANALYZING")
            run_multithread_service(citations_dir=analysis_path, paper_id=paper_id)
            db_analysis.update_paper(paper_id, user_id=uid, analysis_status="COMPLETED")
        except Exception as e:
            print(f"[Analysis Error][paper_id={paper_id}] {e}")
            try:
                db_analysis.update_paper(
                    paper_id, user_id=uid,
                    analysis_status="ANALYSIS_FAILED",
                    analysis_error=str(e),
                )
            except Exception:
                pass
        finally:
            _release_paper(paper_id)

    thread = threading.Thread(target=background_task, daemon=True)
    thread.start()

    return make_response(
        True,
        200,
        f"start analysis paper {paper_id}",
        data={"paper_id": paper_id}
    )


@analysis_bp.route("/single_analysis/<int:paper_id>/<int:citation_id>", methods=["POST"])
@token_required
def start_single_analysis(paper_id: int, citation_id: int):
    """
    启动单片（单个 citation）分析任务：接口仅负责触发，不做复杂逻辑
    """
    paper = db_analysis.get_paper(paper_id, user_id=get_current_user_id())
    if not paper:
        return make_response(False, 404, "paper not found", None)
    analysis_path = os.path.join("storage", "papers", str(paper_id), "citations")

    if not os.path.exists(analysis_path):
        return make_response(
            success=False,
            code=404,
            message="analysis path not found",
            data={"paper_id": paper_id, "citation_id": citation_id}
        )

    if not _try_acquire_paper(paper_id):
        return make_response(
            False, 409,
            "another analysis task is running for this paper",
            {"paper_id": paper_id, "citation_id": citation_id},
        )

    uid = get_current_user_id()

    def background_task():
        try:
            db_analysis.update_paper(paper_id, user_id=uid, analysis_status="ANALYZING")
            run_single_citation_analysis(
                citations_dir=analysis_path,
                citation_id=citation_id,
                paper_id=paper_id,
                mode="minimal",
            )
            db_analysis.update_paper(paper_id, user_id=uid, analysis_status="COMPLETED")
        except Exception as e:
            print(f"[Single Analysis Error][paper_id={paper_id}][citation_id={citation_id}] {e}")
            try:
                db_analysis.update_paper(
                    paper_id, user_id=uid,
                    analysis_status="ANALYSIS_FAILED",
                    analysis_error=str(e),
                )
            except Exception:
                pass
        finally:
            _release_paper(paper_id)

    thread = threading.Thread(target=background_task, daemon=True)
    thread.start()

    return make_response(
        True,
        200,
        f"start single analysis paper {paper_id} citation {citation_id}",
        data={"paper_id": paper_id, "citation_id": citation_id}
    )


# 下载并分析（使用 download_service：引文落库 + 并行下载 PDF）
@analysis_bp.route("/analysis_download/<int:paper_id>", methods=["POST"])
@token_required
def download_and_analysis_all_citations_by_id(paper_id):
    paper = db_analysis.get_paper(paper_id, user_id=get_current_user_id())
    if not paper:
        return make_response(False, 404, "paper not found", None)
    paper_name = paper["title"]

    # 防重复触发
    if not _try_acquire_paper(paper_id):
        return make_response(
            False, 409,
            "another task is already running for this paper",
            {"paper_id": paper_id, "status": paper.get("analysis_status")},
        )
    if (paper.get("analysis_status") or "").upper() in _RUNNING_STATUSES:
        _release_paper(paper_id)
        return make_response(
            False, 409,
            "download/analysis already in progress",
            {"paper_id": paper_id, "status": paper.get("analysis_status")},
        )

    uid = get_current_user_id()

    def background_task():
        analysis_path = os.path.join(
            "storage", "papers", str(paper_id), "citations"
        )
        # 1) 下载：从 API 拉取引文、落库、并行下载 PDF
        try:
            db_analysis.update_paper(
                paper_id, user_id=uid,
                analysis_status="DOWNLOADING", analysis_error=None,
            )
            download_all_citations_for_paper(paper_id)
        except Exception as e:
            err_msg = str(e)
            print(f"[Download Error][paper_id={paper_id}][title={paper_name}] {err_msg}")
            try:
                db_analysis.update_paper(
                    paper_id, user_id=uid,
                    analysis_status="DOWNLOAD_FAILED",
                    analysis_error=err_msg,
                )
            except Exception:
                pass
            return

        # 2) 分析：状态 ANALYZING → COMPLETED
        try:
            db_analysis.update_paper(
                paper_id, user_id=uid,
                analysis_status="ANALYZING", analysis_error=None,
            )
            run_multithread_service(citations_dir=analysis_path, paper_id=paper_id)
            db_analysis.update_paper(
                paper_id, user_id=uid,
                analysis_status="COMPLETED", analysis_error=None,
            )
        except Exception as e:
            err_msg = str(e)
            print(f"[Analysis Error][paper_id={paper_id}][title={paper_name}] {err_msg}")
            try:
                db_analysis.update_paper(
                    paper_id, user_id=uid,
                    analysis_status="ANALYSIS_FAILED",
                    analysis_error=err_msg,
                )
            except Exception:
                pass
        finally:
            _release_paper(paper_id)

    thread = threading.Thread(target=background_task, daemon=True)
    thread.start()
    return make_response(True, 200, f"start to download and analysis for {paper_name}", None)


@analysis_bp.route("/analysis/<int:paper_id>/summarize", methods=["POST"])
@token_required
def start_summarize_analysis(paper_id: int):
    """
    异步启动分析总结任务，后台执行 run_summarize_analysis，
    结果写入 storage/papers/{paper_id}/citations/summarize_report.json。
    立即返回，用 GET 请求轮询获取结果。
    """
    paper = db_analysis.get_paper(paper_id, user_id=get_current_user_id())
    if not paper:
        return make_response(False, 404, "paper not found", None)

    analysis_path = os.path.join("storage", "papers", str(paper_id), "citations")
    report_path = os.path.join(analysis_path, "multiprocess_analysis_report.json")

    if not os.path.exists(report_path):
        return make_response(
            False,
            404,
            "analysis report not found, please run analysis first",
            {"paper_id": paper_id},
        )

    if not _try_acquire_paper(paper_id):
        return make_response(
            False, 409,
            "another task is running for this paper",
            {"paper_id": paper_id},
        )

    def background_task():
        try:
            run_summarize_analysis(citations_dir=analysis_path, paper_id=paper_id)
        except Exception as e:
            print(f"[Summarize Error][paper_id={paper_id}] {e}")
        finally:
            _release_paper(paper_id)

    thread = threading.Thread(target=background_task, daemon=True)
    thread.start()

    return make_response(
        True,
        200,
        "summarize started, use GET /analysis/<paper_id>/summarize to fetch result",
        {"paper_id": paper_id},
    )


@analysis_bp.route("/analysis/<int:paper_id>/summarize", methods=["GET"])
@token_required
def get_summarize_result(paper_id: int):
    """
    获取分析总结结果，从 storage/papers/{paper_id}/citations/summarize_report.json 读取。
    若文件不存在则返回 404（可能总结尚未完成或未执行）。
    """
    paper = db_analysis.get_paper(paper_id, user_id=get_current_user_id())
    if not paper:
        return make_response(False, 404, "paper not found", None)

    summary_path = os.path.join(
        "storage", "papers", str(paper_id), "citations", "summarize_report.json"
    )

    if not os.path.exists(summary_path):
        return make_response(
            False,
            404,
            "summarize report not found, please run summarize first or wait for completion",
            {"paper_id": paper_id},
        )

    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            summation = json.load(f)
        return make_response(True, 200, "success", summation)
    except Exception as e:
        return make_response(False, 500, str(e), None)
