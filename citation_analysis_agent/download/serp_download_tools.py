from model.model import DatabaseModel
from download.download_from_serp import *
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def build_storage_paths(base_dir, paper_db_id):
    """
    创建论文目录：
    storage/papers/{paper_id}/citations/
    """
    root = os.path.join(base_dir, "papers", str(paper_db_id))
    citations_dir = os.path.join(root, "citations")

    ensure_dir(root)
    ensure_dir(citations_dir)

    return {
        "root": root,
        "citations": citations_dir,
    }

def download_all_citations_by_name(paper_name, paper_db_id,storage_root="storage",url=None):
    db=DatabaseModel()
    paths = build_storage_paths(storage_root, paper_db_id)
    citation_dir = paths["citations"]
    # 创建目录结构
    if url is None:
        article_info = search_article_and_get_citation_api(paper_name)
        url = article_info['citation_api']
    print("\n=== Step 2: 获取所有引用文章 ===")
    citations = fetch_all_citations(url)
    json_path=os.path.join(citation_dir, "data.json")
    result_path = os.path.join(citation_dir, "result.json")
    with open(json_path, "w", encoding="utf-8") as f:
        import json
        json.dump(citations, f, ensure_ascii=False, indent=4)

    create_scholar_json(citation_dir, 'info.json', title=paper_name)
    db.update_paper(paper_db_id, analysis_status="DOWNLOADING")

    result=download_pdfs_from_json(json_path,citation_dir,result_path)
    db.update_paper(paper_db_id, analysis_status="DOWNLOADED")
    return result


def download_all_citations_by_id(paper_id, storage_root="storage"):
    db = DatabaseModel()
    paper = db.get_paper(paper_id)
    paper_name = paper['title']
    cite_link=paper['cite_link']
    print(cite_link)
    return download_all_citations_by_name(paper_name, paper_id, storage_root,url=cite_link)
if __name__ == "__main__":
    download_all_citations_by_id(2)