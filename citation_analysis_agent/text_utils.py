from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Optional, Tuple, Dict

import fitz  # PyMuPDF
from fuzzywuzzy import fuzz

try:
    from .schema import PaperInfo, PaperSection
    from .model.model import DatabaseModel
    from .model.citation_model import CitationModel
except ImportError:
    from schema import PaperInfo, PaperSection
    from model.model import DatabaseModel
    from model.citation_model import CitationModel
import string


def _resolve_paper_id(paper_id: str | Path) -> Optional[int]:
    """从 paper_id 或路径中解析数值 ID。"""
    if isinstance(paper_id, Path):
        candidate = paper_id.name
    else:
        candidate = str(paper_id)
    if candidate.isdigit():
        return int(candidate)
    try:
        name = Path(candidate).name
    except Exception:
        return None
    return int(name) if name.isdigit() else None


def _get_db_path() -> str:
    return os.getenv("CITATION_DB_PATH", "citation_analysis.db")


def load_paper_info(paper_id: str, info_file_path: Optional[str] = None) -> PaperInfo:
    """读取论文元数据，优先从数据库获取。"""
    resolved_id = _resolve_paper_id(paper_id)
    db = DatabaseModel(db_path=_get_db_path())
    try:
        if resolved_id is not None:
            paper = db.get_paper(resolved_id)
            if paper:
                return PaperInfo(
                    scholar_id=paper.get("result_id"),
                    authors=paper.get("authors") or [],
                    approach_name=paper.get("approach_name") or [],
                    title=paper.get("title") or "",
                    venue=paper.get("venue") or "",
                    year=str(paper.get("year") or ""),
                )
    finally:
        db.close()

    info_file_path = info_file_path or os.path.join(paper_id, "info.json")
    with open(info_file_path, "r", encoding="utf-8") as file:
        info_data = json.load(file)
    return PaperInfo(
        scholar_id=info_data.get("ScholarID"),
        authors=info_data.get("Authors", []),
        approach_name=info_data.get("ApproachName", []) or [],
        title=info_data.get("Title", ""),
        venue=info_data.get("Venue", ""),
        year=str(info_data.get("Year", "")),
    )


def get_citing_paper_name(paper_id: str, citation_id: int):
    resolved_id = _resolve_paper_id(paper_id)
    db = CitationModel(db_path=_get_db_path())
    try:
        if resolved_id is not None:
            citation = db.get_citation(resolved_id, citation_id)
            if citation:
                return citation.get("title")
    finally:
        db.close()

    info_file_path = os.path.join(paper_id, "result.json")
    with open(info_file_path, "r", encoding="utf-8") as file:
        data_data = json.load(file)

    for item in data_data:
        if item.get("id") == citation_id:
            return item.get("title")
    return None


def discover_citation_ids(paper_path: Path) -> List[int]:
    """从数据库获取该论文下已下载的 Citation ID 列表。"""
    resolved_id = _resolve_paper_id(paper_path)
    db = CitationModel(db_path=_get_db_path())
    try:
        if resolved_id is not None:
            citations = db.get_citations_by_paper(resolved_id)
            return [
                c.get("citation_id")
                for c in citations
                if c.get("citation_id") is not None
                and c.get("download_status") in ("success", "exists")
            ]
    finally:
        db.close()

    ids = set()
    for entry in paper_path.iterdir():
        match = re.match(r"Citation_(\d+)\.(?:pdf|txt|json)$", entry.name)
        if match:
            ids.add(int(match.group(1)))
    return sorted(ids)


def pdf_to_text(pdf_path: Path) -> str:
    """将 PDF 转换为纯文本。"""
    with fitz.open(pdf_path) as doc:
        pages = [page.get_text() for page in doc]
    return "\n".join(pages)


def remove_extra_linebreaks(text: str) -> str:
    """移除多余的换行符，保留段落结构。"""
    # 统计每行长度
    lines = text.splitlines()
    line_lengths = [len(line) for line in lines if line]
    avg_length = sum(line_lengths) / len(line_lengths) if line_lengths else 0
    refined_lengths = [len(line) for line in lines if len(line) >= avg_length * 0.7] 
    refined_avg = sum(refined_lengths) / len(refined_lengths) if refined_lengths else 0
    
    result_text = ""
    for i, line in enumerate(lines):
        if 0.85 * refined_avg < len(line) < 1.15 * refined_avg:
            result_text += line + " "
        else:
            result_text += line + "\n"
    
    return result_text.strip()


def load_citation_text(paper_id: str, citation_id: int) -> str:
    """从数据库读取引用路径，读取全文（txt/pdf）。"""
    resolved_id = _resolve_paper_id(paper_id)
    db = CitationModel(db_path=_get_db_path())
    try:
        if resolved_id is not None:
            citation = db.get_citation(resolved_id, citation_id)
            if citation and citation.get("path"):
                citation_path = Path(citation["path"])
                if citation_path.exists():
                    if citation_path.suffix.lower() == ".txt":
                        return citation_path.read_text(encoding="utf-8")
                    if citation_path.suffix.lower() == ".pdf":
                        text = pdf_to_text(citation_path)
                        text = remove_extra_linebreaks(text)
                        txt_path = citation_path.with_suffix(".txt")
                        txt_path.write_text(text, encoding="utf-8")
                        return text
    finally:
        db.close()

    txt_path = Path(paper_id) / f"Citation_{citation_id}.txt"
    if not txt_path.exists():
        pdf_path = Path(paper_id) / f"Citation_{citation_id}.pdf"
        if not pdf_path.exists():
            raise FileNotFoundError(f"Missing Citation_{citation_id}.txt/pdf in {paper_id}")
        text = pdf_to_text(pdf_path)
        text = remove_extra_linebreaks(text)
        txt_path.write_text(text, encoding="utf-8")
    return txt_path.read_text(encoding="utf-8")


def load_primary_text(
    paper_path: Path,
    override_path: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """加载原论文全文（txt/pdf），优先使用数据库中记录的路径。"""
    candidates: List[Path] = []
    if override_path:
        candidates.append(Path(override_path))

    resolved_id = _resolve_paper_id(paper_path)
    db = DatabaseModel(db_path=_get_db_path())
    try:
        if resolved_id is not None:
            paper = db.get_paper(resolved_id)
            if paper:
                link_path = paper.get("link")
                cite_link_path = paper.get("cite_link")
                for path_value in (link_path, cite_link_path):
                    if path_value:
                        candidates.append(Path(path_value))
    finally:
        db.close()

    candidates.extend([paper_path / "paper.txt", paper_path / "paper.pdf"])

    for candidate in candidates:
        if not candidate.exists():
            continue
        if candidate.suffix.lower() == ".txt":
            return candidate.read_text(encoding="utf-8"), str(candidate)
        if candidate.suffix.lower() == ".pdf":
            return pdf_to_text(candidate), str(candidate)
    return None, None


def build_sections(
    primary_text: str,
    primary_source: Optional[str],
    chunk_size: int,
    chunk_overlap: int,
) -> List[PaperSection]:
    """将原文切分为重叠窗口，后续用于匹配引用片段。"""
    sections: List[PaperSection] = []
    text_len = len(primary_text)
    cursor = 0
    section_idx = 1

    while cursor < text_len:
        end = min(text_len, cursor + chunk_size)
        chunk = primary_text[cursor:end]
        title = guess_section_title(primary_text, cursor)
        sections.append(
            PaperSection(
                section_id=f"S{section_idx}",
                title=title,
                text=chunk,
                start=cursor,
                end=end,
                source=primary_source,
            )
        )
        cursor = end - chunk_overlap
        section_idx += 1
        if cursor < 0:
            cursor = 0

    return sections


def guess_section_title(text: str, cursor: int) -> str:
    """尝试从上下文推测段落标题。"""
    window = text[max(0, cursor - 200) : cursor]
    for line in reversed(window.splitlines()):
        clean = line.strip()
        if not clean:
            continue
        if len(clean) < 80 and (clean.isupper() or re.match(r"^\d+(\.\d+)*\s+", clean)):
            return clean
    preview = text[cursor : cursor + 80].splitlines()
    return preview[0].strip() if preview else "Section"


def build_snippets(
    citation_text: str,
    positions: List[Tuple[int, int]],
    snippet_length: int = 1000,
) -> List[Dict[str, any]]:
    """根据引用位置裁剪上下文，并合并重叠片段。"""
    if not positions:
        return []

    spans: List[Tuple[int, int]] = []
    for start, end in positions:
        snippet_start = max(0, start - snippet_length // 2)
        snippet_end = min(len(citation_text), end + snippet_length // 2)
        if not spans or spans[-1][1] < snippet_start:
            spans.append((snippet_start, snippet_end))
        else:
            spans[-1] = (spans[-1][0], max(spans[-1][1], snippet_end))

    snippets = []
    for idx, (start, end) in enumerate(spans, start=1):
        # 美化snippet文本，避免截断句子
        snippet_text = citation_text[start:end]
        # snippet_text_list = snippet_text.split('.')
        # if len(snippet_text_list) > 3:
        #     snippet_text = '.'.join(snippet_text_list[1:-1]).strip()
        # else:
        #     snippet_text = '.'.join(snippet_text_list).strip()
        snippets.append(
            {
                "index": idx,
                "span": (start, end),
                "text": snippet_text,
            }
        )
    
    # 最后一个snippet常为参考文献列表中的条目，去掉它
    if len(snippets) > 1:
        snippets = snippets[:-1]
        
    return snippets


def match_sections(
    snippet_text: str,
    sections: List[PaperSection],
    top_k: int = 3,
) -> List[dict]:
    """使用 SequenceMatcher 计算相似度，返回最可能的段落。"""
    scored = []
    for section in sections:
        if not section.text.strip():
            continue
        ratio = SequenceMatcher(None, snippet_text.lower(), section.text.lower()).ratio()
        scored.append(
            {
                "section_id": section.section_id,
                "title": section.title,
                "score": round(ratio, 4),
                "anchor": f"{section.source}#char={section.start}" if section.source else None,
                "excerpt": section.text[:400].strip(),
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def extract_references(title: str, paper_text: str) -> Optional[int]:
    """参照 common.py 实现，从参考文献区域推断与标题最接近的编号。"""
    reference_titles = ["References", "Bibliography", "Works Cited", "参考文献"]
    reference_start = None
    for rt in reference_titles:
        matches = list(re.finditer(rf"^\s*{rt}\s*$", paper_text, re.IGNORECASE | re.MULTILINE))
        match = matches[0] if matches else None
        if match:
            reference_start = match.start()
            break
    if reference_start is None:
        reference_start = 0

    window_size = min(len(title) + 20, 100)
    max_similarity = 0
    match_position = -1
    for i in range(reference_start, len(paper_text) - window_size + 1):
        window_text = paper_text[i : i + window_size]
        similarity = fuzz.ratio(title.lower(), window_text.lower())
        if similarity > max_similarity:
            max_similarity = similarity
            match_position = i
    if match_position == -1:
        return None

    analysis_length = 1000
    expected_consecutive_numbers = 3
    distance_to_start = (
        analysis_length // 2
        if match_position - reference_start > analysis_length // 2
        else match_position - reference_start
    )
    distance_to_end = (
        analysis_length // 2
        if len(paper_text) - match_position > analysis_length // 2
        else len(paper_text) - match_position
    )
    snippet = paper_text[
        max(match_position - (analysis_length - distance_to_end), reference_start) : min(
            match_position + (analysis_length - distance_to_start), len(paper_text)
        )
    ]

    all_patterns = [r"\[\s*(\d+)\s*\]", r"\b(\d+)\s*\.", r"^\s*(\d+)\s*$"]

    def contains_subsequence(nums: List[int], expected: int) -> bool:
        dp = {}
        for num in nums:
            prev = num - 1
            current_length = dp.get(prev, 0) + 1
            if current_length >= expected:
                return True
            if current_length > dp.get(num, 0):
                dp[num] = current_length
        return False

    patterns = []
    if len(snippet) < analysis_length:
        patterns = all_patterns
    else:
        for pattern in all_patterns:
            matches = re.findall(pattern, snippet, re.MULTILINE)
            numbers = [
                int(match)
                for match in matches
                if match.isdigit() and 0 <= int(match) <= 1500
            ]
            if contains_subsequence(numbers, expected_consecutive_numbers):
                patterns.append(pattern)
                break
        if not patterns:
            return None

    search_text = paper_text[match_position - 500 : match_position + 10]

    def find_last_match(search_text: str, patterns: List[str]):
        last_match = None
        last_pos = -1
        for pattern in patterns:
            matches = list(re.finditer(pattern, search_text, re.IGNORECASE | re.MULTILINE))
            match = matches[-1] if matches else None
            if match is None:
                continue
            if match.start() > last_pos:
                last_match = match
                last_pos = match.start()
        return last_match

    match = find_last_match(search_text, patterns)
    return int(match.group(1)) if match else None


def extract_year_alphabet(title: str, paper_text: str, year: str) -> str:
    """从字符串中提取年份后缀字母（如 2020a）。"""
    reference_titles = ["References", "Bibliography", "Works Cited", "参考文献"]
    reference_start = None
    for rt in reference_titles:
        matches = list(re.finditer(rf"^\s*{rt}\s*$", paper_text, re.IGNORECASE | re.MULTILINE))
        match = matches[0] if matches else None
        if match:
            reference_start = match.start()
            break
    if reference_start is None:
        reference_start = 0
        
    window_size = min(len(title) + 20, 100)
    max_similarity = 0
    match_position = -1
    for i in range(reference_start, len(paper_text) - window_size + 1):
        window_text = paper_text[i : i + window_size]
        similarity = fuzz.ratio(title.lower(), window_text.lower())
        if similarity > max_similarity:
            max_similarity = similarity
            match_position = i
    
    # print("年份后缀字母匹配位置:", match_position)
    # print(paper_text[match_position:match_position+50])
    if match_position == -1:
        return None
    
    search_text = paper_text[match_position - 10: match_position + 500]
    translator = str.maketrans('', '', string.punctuation)
    title_elements = [item.lower().translate(translator) for item in title.split()]
    paper_text_elements = [item.lower().translate(translator) for item in search_text.split()]
    matched_indices = -1
    for i in range(len(paper_text_elements) - len(title_elements) + 1):
        if paper_text_elements[i:i + len(title_elements)] == title_elements:
            matched_indices = i + len(title_elements) - 1
            break
    if matched_indices == -1:
        return None
    
    year_pattern = rf"{re.escape(year)}([a-zA-Z]?)"
    year_match = re.search(year_pattern, ' '.join(paper_text_elements[matched_indices:]))
    year_alphabet = year_match.group(1) if year_match else None
    return year_alphabet


def extract_citation_positions(
    paper_text: str,
    authors: List[str],
    year: str,
    reference_number: Optional[int] = None,
    method_names: Optional[List[str]] = None,
    year_alphabet: Optional[str] = None,
) -> List[Tuple[int, int]]:
    """匹配数字引用 / 作者年份 / 方法名称，返回字符区间。"""
    method_names = method_names or []
    results: List[Tuple[int, int]] = []

    if reference_number is not None:
        numeric_pattern = r"\[([0-9\,\-\–\s\[\]]+)\]"
        numeric_matches = re.finditer(numeric_pattern, paper_text)
        for match in numeric_matches:
            elements = (
                match.group(1)
                .replace(" ", "")
                .replace("][", ",")
                .replace("]-[", "-")
                .replace("]–[", "–")
                .split(",")
            )
            found = False
            for elem in elements:
                elem = elem.strip('[]')
                if "-" in elem or "–" in elem:
                    parts = re.split(r"[-–]", elem)
                    if len(parts) != 2:
                        continue
                    try:
                        start_num = int(parts[0].strip())
                        end_num = int(parts[1].strip())
                    except ValueError:
                        continue
                    if start_num <= reference_number <= end_num:
                        found = True
                        break
                else:
                    try:
                        num = int(elem.strip())
                    except ValueError:
                        continue
                    if num == reference_number:
                        found = True
                        break
            if found:
                results.append((match.start(), match.end()))

    if authors:
        surnames = [name.split()[-1] for name in authors]
        separator = r"(?:\s+and\s+|\s*&\s*|\s*,\s*|\s+)"
        author_pattern = rf"(?P<name0>{surnames[0]}){separator}+"
        for i in range(1, len(surnames)):
            author_pattern += rf"((?P<name{i}>{surnames[i]}){separator}+)?"
        if year_alphabet:
            author_pattern += rf"(?P<etal>et\s+al\.?)?\s*(,\s*)?(?:\(\s*{year}(?P<alphabet1>[a-z;]*)\s*\)|{year}(?P<alphabet2>[a-z;]*)|\[\s*{year}(?P<alphabet3>[a-z;]*)\s*\])"
        else:
            author_pattern += rf"(?P<etal>et\s+al\.?)?\s*(,\s*)?(?:\(\s*{year}\s*\)|{year}|\[\s*{year}\s*\])"
        author_regex = re.compile(author_pattern, re.IGNORECASE)
        for match in author_regex.finditer(paper_text):
            if match.group("etal") and match.group(f"name{len(surnames) - 1}"):
                continue
            if not match.group("etal") and not match.group(f"name{len(surnames) - 1}"):
                continue
            if year_alphabet:
                if not (year_alphabet in (match.group("alphabet1") or "")) and not (
                    year_alphabet in (match.group("alphabet2") or "")
                ) and not (year_alphabet in (match.group("alphabet3") or "")):
                    continue
            results.append((match.start(), match.end()))

    for method_name in method_names:
        if not method_name:
            continue
        method_pattern = rf"\b{re.escape(method_name)}\b"
        method_regex = re.compile(method_pattern)
        for match in method_regex.finditer(paper_text):
            results.append((match.start(), match.end()))
            
    results.sort(key=lambda x: x[0])
    return results


# with open("/data/citation_analysis/citation_analysis_agent_test/papers/70/citations/Citation_35.txt", 'r') as f:
#     citation_text = f.read()

# reference_number = extract_references(
#     title="Codedpo: Aligning code models with self generated and verified source code",
#     paper_text=citation_text,
# )

# print("引用编号:", reference_number)

# year_alphabet = extract_year_alphabet(
#     title="Codedpo: Aligning code models with self generated and verified source code",
#     paper_text=citation_text,
#     year="2025",
# )

# print("年份后缀字母:", year_alphabet)

# positions = extract_citation_positions(
#     paper_text=citation_text,
#     authors=[
#         "Kechi Zhang",
#         "Ge Li",
#         "Yihong Dong",
#         "Jingjing Xu",
#         "Jun Zhang",
#         "Jing Su",
#         "Yongfei Liu",
#         "Zhi Jin"
#     ],
#     year="2025",
#     reference_number=reference_number,
#     method_names=["CodedPo"],
#     year_alphabet=year_alphabet,
# )

# snippets = build_snippets(citation_text, positions)
# for snippet in snippets:
#     print(snippet)