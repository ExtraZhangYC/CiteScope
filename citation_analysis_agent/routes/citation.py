"""
引文相关路由：查询、上传 PDF 等。
"""

from flask import Blueprint, request

from model.model import DatabaseModel
from utils.response import make_response
from utils.auth import token_required, get_current_user_id
from service.citations_service import (
    get_citations_for_paper,
    upload_citation_pdf,
)

citation_bp = Blueprint("citation", __name__)
db = DatabaseModel()


# -----------------------------------------------------------------------------
# 1. 查询某篇 paper 的所有引文
# -----------------------------------------------------------------------------


@citation_bp.route("/papers/<int:paper_id>/citations", methods=["GET"])
@token_required
def list_citations(paper_id):
    """
    查询某篇论文的全部引文信息（从 citations 表）。
    """
    paper = db.get_paper(paper_id, user_id=get_current_user_id())
    if not paper:
        return make_response(False, 404, "paper not found", None)
    try:
        citations = get_citations_for_paper(
            paper_id,
            user_id=get_current_user_id(),
        )
        return make_response(True, 200, "success", {"paper": paper, "citations": citations})
    except ValueError as e:
        return make_response(False, 404, str(e), None)
    except Exception as e:
        return make_response(False, 500, str(e), None)


# -----------------------------------------------------------------------------
# 2. 上传 PDF 并更新下载状态为已下载
# -----------------------------------------------------------------------------


@citation_bp.route(
    "/papers/<int:paper_id>/citations/<int:citation_id>/upload",
    methods=["POST"],
)
@token_required
def upload_pdf(paper_id, citation_id):
    """
    上传某条引文的 PDF，并更新其下载状态为已下载。
    请求：multipart/form-data，字段 file。
    """
    paper = db.get_paper(paper_id, user_id=get_current_user_id())
    if not paper:
        return make_response(False, 404, "paper not found", None)

    if "file" not in request.files:
        return make_response(False, 400, "file is required", None)
    file = request.files["file"]
    if file.filename == "":
        return make_response(False, 400, "empty filename", None)

    try:
        result = upload_citation_pdf(
            paper_id,
            citation_id,
            file,
            user_id=get_current_user_id(),
        )
        return make_response(
            True,
            200,
            "upload success",
            result,
        )
    except ValueError as e:
        return make_response(False, 404, str(e), None)
    except Exception as e:
        return make_response(False, 500, str(e), None)
