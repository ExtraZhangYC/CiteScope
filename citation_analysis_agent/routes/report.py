"""
报告路由：创建联合报告、列表、下载
"""
import os
import threading

from flask import Blueprint, request, send_file
from model.model import DatabaseModel
from service.report_service import (
    add_report,
    get_report,
    list_reports,
    run_combined_report_task,
    delete_report,
)
from utils.response import make_response
from utils.auth import token_required, get_current_user_id

report_bp = Blueprint("report", __name__)
db = DatabaseModel()


def _report_name_from_paper_ids(paper_ids):
    """生成报告名称：id为1，2，3的联合报告"""
    ids_str = "，".join(str(pid) for pid in sorted(paper_ids))
    return f"id为{ids_str}的联合报告"


@report_bp.route("/reports", methods=["POST"])
@token_required
def create_report():
    """
    根据论文 ID 列表创建异步联合报告任务。
    Body: { "paper_ids": [1, 2, 3], "name": "可选报告名称" }
    若未传 name 或为空，则自动生成名称（如 id为1，2，3的联合报告）。
    立即返回 report_id，后台异步生成报告。
    """
    data = request.get_json(silent=True) or {}
    paper_ids = data.get("paper_ids")
    if not paper_ids or not isinstance(paper_ids, list):
        return make_response(False, 400, "paper_ids is required (list of int)", None)
    custom_name = (data.get("name") or data.get("report_name") or "").strip()

    try:
        paper_ids = [int(x) for x in paper_ids]
    except (ValueError, TypeError):
        return make_response(False, 400, "paper_ids must be list of integers", None)

    if not paper_ids:
        return make_response(False, 400, "paper_ids cannot be empty", None)

    uid = get_current_user_id()

    for pid in paper_ids:
        paper = db.get_paper(pid, user_id=uid)
        if not paper:
            return make_response(
                False,
                403,
                f"paper_id={pid} not found or access denied",
                None,
            )

    name = custom_name if custom_name else _report_name_from_paper_ids(paper_ids)
    report_id = add_report(
        user_id=uid,
        name=name,
        paper_ids=paper_ids,
        paper_count=len(paper_ids),
        status="analysis",
    )

    def background_task():
        run_combined_report_task(
            report_id=report_id,
            user_id=uid,
            paper_ids=paper_ids,
        )

    thread = threading.Thread(target=background_task, daemon=True)
    thread.start()

    return make_response(
        True,
        201,
        "report task started, poll GET /reports/<id> for status",
        {"report_id": report_id, "name": name},
    )


@report_bp.route("/reports", methods=["GET"])
@token_required
def list_user_reports():
    """返回当前用户的全部报告"""
    uid = get_current_user_id()
    reports = list_reports(user_id=uid)
    return make_response(True, 200, "success", reports)


@report_bp.route("/reports/<int:report_id>", methods=["GET"])
@token_required
def get_report_detail(report_id: int):
    """获取单条报告详情"""
    uid = get_current_user_id()
    report = get_report(report_id, user_id=uid)
    if not report:
        return make_response(False, 404, "report not found", None)
    return make_response(True, 200, "success", report)


@report_bp.route("/reports/<int:report_id>", methods=["DELETE"])
@token_required
def remove_report(report_id: int):
    """删除单条报告"""
    uid = get_current_user_id()
    ok = delete_report(report_id, user_id=uid)
    return make_response(ok, 200 if ok else 404, "success" if ok else "report not found", None)


@report_bp.route("/reports/<int:report_id>/download", methods=["GET"])
@token_required
def download_report(report_id: int):
    """
    下载报告文件。查询参数 format=pdf|html，默认 pdf。
    """
    uid = get_current_user_id()
    report = get_report(report_id, user_id=uid)
    if not report:
        return make_response(False, 404, "report not found", None)

    fmt = (request.args.get("format") or "pdf").strip().lower()
    if fmt not in ("pdf", "html"):
        return make_response(False, 400, "format must be pdf or html", None)

    path_key = "pdf_path" if fmt == "pdf" else "html_path"
    file_path = report.get(path_key)
    if not file_path or not os.path.isfile(file_path):
        return make_response(
            False,
            404,
            f"{fmt} file not found, report may still be generating",
            None,
        )

    ext = ".pdf" if fmt == "pdf" else ".html"
    download_name = f"report_{report_id}{ext}"
    return send_file(
        file_path,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/pdf" if fmt == "pdf" else "text/html",
    )
