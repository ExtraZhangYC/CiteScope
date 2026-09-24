from serpapi import GoogleSearch
import json
import requests
import os

# 从 .env 读取 SerpApi key
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SERPAPI_KEY = os.getenv("SERP_API_KEY", "")
if not SERPAPI_KEY:
    raise ValueError("SERP_API_KEY not found in environment, please check .env file")


def get_paper_from_author_id(author_id):
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
