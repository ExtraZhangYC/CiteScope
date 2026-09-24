"""
论文相关路由：CRUD、模糊搜索、下载等。
"""

from flask import Blueprint, request
import threading

from utils.response import make_response
from utils.auth import token_required, get_current_user_id
from service.paper_service import (
    get_paper,
    list_papers,
    add_paper,
    update_paper,
    delete_paper,
)
from service.download_service import download_all_citations_for_paper
from download.serp_download_tools import (
    fuzzy_search_articles_and_get_citation_api,
)
from download.download_from_serp import (
    get_paper_from_author_id,
)
import os
import json

paper_bp = Blueprint("paper", __name__)


# ============================
# 1. 原始论文 CRUD（需登录，按当前用户隔离）
# ============================


@paper_bp.route("/papers/fuzzy_search", methods=["GET"])
@token_required
def fuzzy_search_paper():
    title = request.args.get("title", "").strip()
    if not title:
        return make_response(False, 400, "title parameter is required", None)
    try:
        results = fuzzy_search_articles_and_get_citation_api(title)
        return make_response(True, 200, "success", results)
    except Exception as e:
        return make_response(False, 500, f"fuzzy search failed: {str(e)}", None)


@paper_bp.route("/papers", methods=["POST"])
@token_required
def create_paper():
    data = request.json or {}
    print("paper create data:", data)
    user_id = get_current_user_id()
    ALLOWED_PAPER_FIELDS = {
        "title", "result_id", "approach_name", "authors", "cite_link",
        "link", "citation_number", "summary", "year", "venue",
    }
    filtered_data = {k: v for k, v in data.items() if k in ALLOWED_PAPER_FIELDS}
    try:
        paper_id = add_paper(user_id=user_id, **filtered_data)
        return make_response(True, 200, "success", paper_id)
    except Exception as e:
        return make_response(False, 500, str(e), None)


@paper_bp.route("/papers/<int:paper_id>", methods=["DELETE"])
@token_required
def remove_paper(paper_id):
    ok = delete_paper(paper_id, user_id=get_current_user_id())
    return make_response(ok, 200 if ok else 404, "success" if ok else "paper not found", None)


@paper_bp.route("/papers/<int:paper_id>", methods=["PUT"])
@token_required
def modify_paper(paper_id):
    data = request.json or {}
    ok = update_paper(paper_id, user_id=get_current_user_id(), **data)
    return make_response(ok, 200 if ok else 404, "success" if ok else "paper not found", None)


@paper_bp.route("/papers/<int:paper_id>", methods=["GET"])
@token_required
def get_paper_by_id(paper_id):
    paper = get_paper(paper_id, user_id=get_current_user_id())
    if not paper:
        return make_response(False, 404, "paper not found", None)
    return make_response(True, 200, "success", paper)


@paper_bp.route("/papers", methods=["GET"])
@token_required
def list_all_papers():
    papers = list_papers(user_id=get_current_user_id())
    return make_response(True, 200, "success", papers if papers else [])


# ============================
# 2. 下载引文（查询、上传见 routes/citation.py）
# ============================


@paper_bp.route("/papers/download_citations", methods=["POST"])
@token_required
def download_citations():
    """
    从 request body 读取 paper_id，异步下载该论文的全部引文（落库 + 并行下载 PDF）。
    """
    data = request.get_json(silent=True) or {}
    paper_id = data.get("paper_id")

    if paper_id is None:
        return make_response(False, 400, "paper_id is required", None)

    try:
        paper_id = int(paper_id)
    except (TypeError, ValueError):
        return make_response(False, 400, "paper_id must be integer", None)

    paper = get_paper(paper_id, user_id=get_current_user_id())
    if not paper:
        return make_response(False, 404, "paper not found", None)

    def background_task():
        try:
            download_all_citations_for_paper(paper_id)
        except Exception as e:
            print(f"[Download Error][paper_id={paper_id}] {e}")

    thread = threading.Thread(target=background_task, daemon=True)
    thread.start()
    return make_response(True, 200, f"start to download citations for paper {paper_id}", None)


# ============================
# 3. 作者相关
# ============================


@paper_bp.route("/authors/<author_id>/articles", methods=["GET"])
@token_required
def author_articles(author_id):
    try:
        result = get_paper_from_author_id(author_id)
        return make_response(True, 200, "fetch success and saved", {
            "author_id": author_id,
            "count": len(result) if isinstance(result, list) else None,
            "citations": result,
        })
    except Exception as e:
        return make_response(False, 500, f"fetch author articles failed: {str(e)}", None)


@paper_bp.route("/my/<author_id>/articles", methods=["GET", "POST"])
@token_required
def my_articles(author_id):
    base_dir = os.path.join("storage", "authors", str(author_id))
    os.makedirs(base_dir, exist_ok=True)
    save_path = os.path.join(base_dir, "articles.json")

    if request.method == "GET":
        if not os.path.exists(save_path):
            return make_response(False, 404, "articles.json not found for this author", None)
        try:
            with open(save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return make_response(True, 200, "success", data)
        except Exception as e:
            return make_response(False, 500, f"read articles.json failed: {str(e)}", None)

    if request.method == "POST":
        try:
            result = get_paper_from_author_id(author_id)
        except Exception as e:
            return make_response(False, 500, f"fetch author articles failed: {str(e)}", None)
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return make_response(False, 500, f"write articles.json failed: {str(e)}", None)
        return make_response(True, 200, "fetch success and saved", {
            "author_id": author_id,
            "count": len(result) if isinstance(result, list) else None,
            "path": save_path,
            "citations": result,
        })
