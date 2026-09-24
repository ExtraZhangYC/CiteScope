import requests
from serpapi import GoogleSearch
import os
import json
from typing import List, Optional

# 从 .env 读取 SerpApi key
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SERPAPI_KEY = os.getenv("SERP_API_KEY", "")
if not SERPAPI_KEY:
    raise ValueError("SERP_API_KEY not found in environment, please check .env file")


# ------------------------------------------------------------
#  ① 根据论文名称搜索，返回引用查询 API 链接
# ------------------------------------------------------------
def fuzzy_search_articles_and_get_citation_api(title, max_results=5):
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_scholar",
        "q": title,
        "api_key": SERPAPI_KEY
    }

    resp = requests.get(url, params=params, timeout=30)
    data = resp.json()

    results = data.get("organic_results", [])
    if not results:
        print("[ERR] No paper found for query:", title)
        return []

    fuzzy_results = []
    for item in results:
        if len(fuzzy_results) >= max_results:
            break

        inline_links = item.get("inline_links", {})
        cited_by = inline_links.get("cited_by")
        if not cited_by:
            continue

        citation_api_link = cited_by.get("serpapi_scholar_link")
        total = cited_by.get("total")
        if not citation_api_link:
            continue

        publication_info = item.get("publication_info", {})
        authors = [a.get("name") for a in publication_info.get("authors", [])]

        fuzzy_results.append({
            "title": item.get("title"),
            "result_id": item.get("result_id"),
            "link": item.get("link"),
            "authors": authors,
            "citation_number": total,
            "cite_link": citation_api_link,
            "summary": publication_info.get("summary"),
        })

    return fuzzy_results


def search_article_and_get_citation_api(title):
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_scholar",
        "q": title,
        "api_key": SERPAPI_KEY
    }

    resp = requests.get(url, params=params, timeout=30)
    data = resp.json()

    results = data.get("organic_results", [])
    if not results:
        print("[ERR] No paper found")
        return None

    if len(results) > 1:
        print(f"[WARN] Multiple results, picking the first: {results[0]['title']}")

    first = results[0]
    cited_by = first.get("inline_links", {}).get("cited_by")
    if not cited_by:
        print("[ERR] No citation info for this paper")
        return None

    return {
        "title": first["title"],
        "summary": first.get("publication_info", {}).get("summary"),
        "citation_api": cited_by.get("serpapi_scholar_link"),
    }


# ------------------------------------------------------------
#  ② 根据引用查询链接，获取全部分页引用文章
# ------------------------------------------------------------
def fetch_all_citations(citation_api_url, max_len=500):
    all_citations = []
    next_url = citation_api_url + f"&api_key={SERPAPI_KEY}"

    while next_url:
        resp = requests.get(next_url, timeout=30)
        data = resp.json()
        results = data.get("organic_results", [])
        all_citations.extend(results)
        if len(all_citations) >= max_len:
            break
        next_url = data.get("serpapi_pagination", {}).get("next")
        if next_url:
            next_url += f"&api_key={SERPAPI_KEY}"

    return all_citations


# ------------------------------------------------------------
#  ③ 下载 PDF
# ------------------------------------------------------------
def download_pdfs_from_json(json_path="data.json", output_dir="pdf", result_json="download_result.json"):
    os.makedirs(output_dir, exist_ok=True)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = []
    for idx, item in enumerate(data, start=1):
        item["download"] = {"status": "skipped", "pdf_path": None, "error": None}
        item["id"] = idx

        if "resources" not in item or not item["resources"]:
            item["download"]["error"] = "no resources"
            result.append(item)
            continue

        pdf_url = item["resources"][0].get("link")
        if not pdf_url:
            item["download"]["error"] = "no pdf link"
            result.append(item)
            continue

        pdf_path = os.path.join(output_dir, f"Citation_{idx}.pdf")
        if os.path.exists(pdf_path):
            item["download"]["status"] = "exists"
            item["download"]["pdf_path"] = pdf_path
            result.append(item)
            continue

        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(pdf_url, headers=headers, timeout=20)
            resp.raise_for_status()
            if not resp.content.startswith(b"%PDF"):
                raise ValueError("content is not PDF")
            with open(pdf_path, "wb") as f:
                f.write(resp.content)
            item["download"]["status"] = "success"
            item["download"]["pdf_path"] = pdf_path
        except Exception as e:
            item["download"]["status"] = "failed"
            item["download"]["error"] = str(e)

        result.append(item)

    with open(result_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Download results saved to {result_json}")
    return result


# ------------------------------------------------------------
#  ④ 生成 info.json
# ------------------------------------------------------------
def create_scholar_json(
    dir_path: str,
    file_name: str,
    scholar_id: Optional[str] = "",
    title: Optional[str] = "",
    authors: Optional[List[str]] = None,
    venue: Optional[str] = "",
    year: Optional[str] = ""
):
    if authors is None:
        authors = []

    approach_name = []
    if title and ":" in title:
        approach = title.split(":", 1)[0].strip()
        if approach:
            approach_name = [approach]

    data = {
        "ScholarID": scholar_id or "",
        "ApproachName": approach_name,
        "Title": title or "",
        "Authors": authors,
        "Venue": venue or "",
        "Year": year or ""
    }

    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, file_name)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return file_path


# ------------------------------------------------------------
#  ⑤ 根据 author_id 获取 Google Scholar 作者文章列表
# ------------------------------------------------------------
def get_paper_from_author_id(author_id: str):
    """通过 SerpApi Google Scholar Author 接口获取某作者的所有文章"""
    params = {
        "engine": "google_scholar_author",
        "author_id": author_id,
        "api_key": SERPAPI_KEY
    }
    search = GoogleSearch(params)
    results = search.get_dict()
    articles = results.get("articles", [])

    pagination = results.get("serpapi_pagination", {})
    next_url = pagination.get("next", "")
    while next_url:
        resp = requests.get(next_url + f"&api_key={SERPAPI_KEY}", timeout=30)
        data = resp.json()
        articles.extend(data.get("articles", []))
        next_url = data.get("serpapi_pagination", {}).get("next", "")

    return articles
