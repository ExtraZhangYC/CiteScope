"""
Tools：LangChain Tools 定义
所有供 agents 使用的工具函数

根据LangChain最佳实践：
- 工具只包含不涉及LLM的外部分析流程
- LLM调用应该在agent层面进行，而不是在工具中
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from langchain.tools import tool

# 导入共享模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from text_utils import (
    build_snippets,
    extract_citation_positions,
    extract_references,
    extract_year_alphabet,
    load_citation_text,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def locate_citations(
    paper_id: str,
    citation_id: int,
    paper_info_json: str,
) -> str:
    """
    定位引用片段工具实现。
    
    Args:
        paper_id: 论文目录路径
        citation_id: 引用ID
        paper_info_json: 论文信息的JSON字符串
    
    Returns:
        包含reference_number和snippets的JSON字符串
    """
    from schema import PaperInfo
    
    try:
        # 解析论文信息
        paper_info_dict = json.loads(paper_info_json)
        paper_info = PaperInfo(**paper_info_dict)
        
        # 开始定位引用片段
        logger.info(
            "[locate] 开始定位引用片段 - Paper: %s, Citation_%s",
            paper_id,
            citation_id,
        )
        
        # 加载引用文本
        citation_text = load_citation_text(paper_id, citation_id)
        logger.debug("[locate] 加载引用文本，长度: %d 字符", len(citation_text))
        
        # 提取引用编号
        reference_number = extract_references(paper_info.title, citation_text)
        logger.info("[locate] 提取的引用编号: %s", reference_number)
        
        year_alphabet = None
        if reference_number is None and paper_info.year:
            year_alphabet = extract_year_alphabet(paper_info.title, citation_text, paper_info.year)
        
        # 提取引用位置
        positions = extract_citation_positions(
            citation_text,
            paper_info.authors,
            paper_info.year,
            reference_number,
            paper_info.approach_name or [],
            year_alphabet
        )
        logger.debug("[locate] 找到 %d 个引用位置", len(positions))
        
        # 构建引用片段
        snippets = build_snippets(citation_text, positions)
        logger.info(
            "[locate] 构建了 %d 个引用片段 - Citation_%s",
            len(snippets),
            citation_id,
        )

        # 记录详细信息
        if not snippets:
            logger.warning(
                "[locate] 未检测到引用片段 - Paper: %s, Citation_%s",
                paper_id,
                citation_id,
            )
        else:
            for i, snippet in enumerate(snippets):
                logger.debug(
                    "[locate] Snippet %d: 文本长度=%d, span=%s",
                    i,
                    len(snippet["text"]),
                    snippet["span"],
                )
        
        # 返回结果
        return json.dumps({
            "reference_number": reference_number,
            "snippets": snippets,
        }, ensure_ascii=False, default=str)
    except Exception as exc:
        logger.exception(f"定位引用片段失败: {exc}")
        return json.dumps({
            "reference_number": None,
            "snippets": [],
            "error": str(exc),
        }, ensure_ascii=False, default=str)


@tool
def locate_citations_tool(
    paper_id: str,
    citation_id: int,
    paper_info_json: str,
) -> str:
    """
    定位引用片段工具。
    
    Args:
        paper_id: 论文目录路径
        citation_id: 引用ID
        paper_info_json: 论文信息的JSON字符串
    
    Returns:
        包含reference_number和snippets的JSON字符串
    """
    return locate_citations(paper_id, citation_id, paper_info_json)


@tool
def extract_snippet_features(
    snippet_text: str,
    snippet_index: int,
    snippet_span: str,
) -> str:
    """
    提取引用片段的基础特征（不涉及LLM分析）。
    
    这是一个纯工具函数，只做文本处理，不包含LLM调用。
    LLM分析应该在agent层面使用专门的分类工具进行。
    
    Args:
        snippet_text: 片段文本
        snippet_index: 片段索引
        snippet_span: 片段位置（格式："(start, end)"）
    
    Returns:
        包含基础特征的JSON字符串
    """
    try:
        # 提取基础特征（如文本长度、是否包含引号等）
        has_quotes = '"' in snippet_text or "'" in snippet_text
        text_length = len(snippet_text)
        word_count = len(snippet_text.split())
        
        return json.dumps({
            "snippet_index": snippet_index,
            "text": snippet_text,
            "span": snippet_span,
            "text_length": text_length,
            "word_count": word_count,
            "has_quotes": has_quotes,
        }, ensure_ascii=False)
    except Exception as exc:
        logger.exception(f"提取片段特征失败: {exc}")
        return json.dumps({
            "snippet_index": snippet_index,
            "error": str(exc),
        }, ensure_ascii=False)


@tool
def prepare_text_for_analysis(
    text: str,
    max_length: int = 8000,
) -> str:
    """
    准备待分析文本（截断过长文本等预处理，不涉及LLM）。
    
    这是一个纯工具函数，只做文本预处理，不包含LLM调用。
    LLM分析应该在agent层面使用专门的工具进行。
    
    Args:
        text: 待分析的文本
        max_length: 最大文本长度
    
    Returns:
        预处理后的文本JSON字符串
    """
    try:
        if len(text) > max_length:
            text = text[:max_length]
            truncated = True
        else:
            truncated = False
        
        return json.dumps({
            "text": text,
            "original_length": len(text),
            "truncated": truncated,
        }, ensure_ascii=False)
    except Exception as exc:
        logger.exception(f"文本预处理失败: {exc}")
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


@tool
def map_sections_tool(
    records_json: str,
    paper_sections_json: str,
) -> str:
    """
    映射片段到章节工具。
    
    Args:
        records_json: 记录列表的JSON字符串
        paper_sections_json: 章节列表的JSON字符串
    
    Returns:
        更新后的记录列表的JSON字符串
    """
    from text_utils import match_sections
    
    records = json.loads(records_json)
    sections = json.loads(paper_sections_json) if paper_sections_json else None
    
    if not sections:
        return records_json
    
    for record in records:
        matches = match_sections(record["text"], sections)
        record["section_matches"] = matches
    
    return json.dumps(records, ensure_ascii=False, default=str)

