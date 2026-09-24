"""
工作流执行函数：使用 Supervisor Agent 模式
让 supervisor agent 自主决定如何协调多个子 agents 进行分析
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .agents import create_supervisor_agent
from .prompt import get_supervisor_user_message
from .utils import extract_json_from_text
from .tools import locate_citations
from text_utils import (
    build_sections,
    discover_citation_ids,
    load_paper_info,
    load_primary_text,
    load_citation_text,
    get_citing_paper_name,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def run_minimal_analysis(
    paper_id: str,
    citation_ids: Optional[List[int]] = None,
    original_paper_path: Optional[str] = None,
    write_output: bool = False,
    chunk_size: int = 1600,
    chunk_overlap: int = 250,
) -> Dict[str, Any]:
    """
    使用 Minimal Analysis 模式运行分析。
    
    不使用 agent，直接调用 LLM，只使用最少的工具（如定位引文段落）。
    参考完整的 agent 运行流程，但简化实现。
    
    Args:
        paper_id: 论文ID（目录路径）
        citation_ids: 要分析的引用ID列表，如果为None则自动发现
        original_paper_path: 原论文路径（未使用，保留以兼容接口）
        write_output: 是否写入输出文件
        chunk_size: 章节切分大小（未使用，保留以兼容接口）
        chunk_overlap: 章节重叠大小（未使用，保留以兼容接口）
    
    Returns:
        分析报告字典
    """
    logger.info("=" * 60)
    logger.info("开始 Minimal Analysis 分析工作流")
    logger.info("=" * 60)
    
    paper_path = Path(paper_id)
    if not paper_path.exists():
        raise FileNotFoundError(f"{paper_id} does not exist.")

    logger.info("加载论文信息: %s", paper_id)
    # 加载论文信息
    paper_info = load_paper_info(str(paper_path))
    logger.info("论文信息: %s", paper_info.citation())

    # 确定要分析的引用ID
    target_ids = citation_ids or discover_citation_ids(paper_path)
    logger.info("发现 %d 个引用ID: %s", len(target_ids), target_ids)
    
    # 准备 paper_info JSON（供工具和 LLM 使用）
    paper_info_json = json.dumps({
        "scholar_id": paper_info.scholar_id,
        "authors": paper_info.authors,
        "approach_name": paper_info.approach_name,
        "title": paper_info.title,
        "venue": paper_info.venue,
        "year": paper_info.year,
    }, ensure_ascii=False)

    # 获取 LLM 实例（不使用 agent）
    from .utils import get_llm, get_llm_config
    from .prompt import get_combined_analysis_system_prompt
    from langchain_core.messages import HumanMessage, SystemMessage
    
    config = get_llm_config()
    logger.info(
        "[minimal] 创建 LLM - Model: %s, Base URL: %s",
        config.model,
        config.base_url,
    )
    llm = get_llm(config)

    # 使用合并分析的系统 prompt（引用分析 + 情感分析）
    # 注意：在 minimal 模式下，snippets 已经通过工具获取并会在用户消息中提供
    system_prompt = get_combined_analysis_system_prompt()

    # 处理每个引用
    aggregated_entries: List[Dict[str, Any]] = []
    all_errors: List[str] = []

    logger.info("开始处理 %d 个引用", len(target_ids))
    for idx, citation_id in enumerate(target_ids, 1):
        logger.info("-" * 60)
        logger.info("处理引用 %d/%d: Citation_%s", idx, len(target_ids), citation_id)
        logger.info("-" * 60)
        
        try:
            # 使用最少的工具：只使用 locate_citations_tool 定位引文段落
            logger.info("[minimal] 使用 locate_citations_tool 定位引用片段 - Citation_%s", citation_id)
            locate_result = locate_citations(
                paper_id=str(paper_path),
                citation_id=citation_id,
                paper_info_json=paper_info_json,
            )

            # 解析定位结果
            locate_data = json.loads(locate_result) if isinstance(locate_result, str) else locate_result
            snippets = locate_data.get("snippets", [])
            reference_number = locate_data.get("reference_number")
            
            logger.info(
                "[minimal] 定位到 %d 个引用片段 - Citation_%s",
                len(snippets),
                citation_id,
            )
            
            # 对每个 snippet 分别调用分析
            citation_citations: List[Dict[str, Any]] = []
            citation_errors: List[str] = []
            approach_names_str = ', '.join(paper_info.approach_name or []) or 'N/A'
            citing_paper_name = get_citing_paper_name(paper_id, citation_id) or ""
            
            if not snippets:
                logger.warning(
                    "[minimal] 未检测到引用片段，启用LLM全文片段定位回退 - Citation_%s",
                    citation_id,
                )
                try:
                    # 读取引文全文（txt优先，pdf回退）
                    citation_full_text = load_citation_text(str(paper_path), int(citation_id))
                    # 片段提取系统提示词
                    extraction_system_prompt = (
                        "你是一个学术引用片段定位助手。\n"
                        "给定引文全文和被引论文信息，请提取最有可能引用被引论文的一个片段（2～3句话）。\n"
                        "只返回片段原文，不要添加解释或额外文本。"
                    )
                    # 构建用户消息
                    cited_authors = ", ".join(paper_info.authors or [])
                    approach_names_str = ', '.join(paper_info.approach_name or []) or 'N/A'
                    user_message_extract = (
                        f"目标被引论文信息：\n"
                        f"- Title: {paper_info.title}\n"
                        f"- Authors: {cited_authors}\n"
                        f"- Year: {paper_info.year}\n"
                        f"- Approach Names: {approach_names_str}\n\n"
                        f"引文全文如下：\n{citation_full_text}"
                    )
                    # 调用LLM进行片段抽取
                    from langchain_core.messages import HumanMessage, SystemMessage
                    extraction_messages = [
                        SystemMessage(content=extraction_system_prompt),
                        HumanMessage(content=user_message_extract),
                    ]
                    extraction_result = llm.invoke(extraction_messages)
                    extracted_text = (
                        extraction_result.content if hasattr(extraction_result, 'content') else str(extraction_result)
                    )
                    extracted_text = (extracted_text or "").strip()
                    # 若成功抽取，构造单一片段并继续分析流程
                    logger.info(
                        "[minimal] LLM回退定位得到片段（长度 %d 字符）",
                        len(extracted_text)
                    )
                    snippets = [{"index": 1, "span": (None, None), "text": extracted_text}]
                except Exception as exc:
                    logger.exception(
                        "[minimal] LLM全文片段定位回退失败 - Citation_%s, 错误: %s",
                        citation_id,
                        exc,
                    )
                    aggregated_entries.append({
                        "id": int(citation_id),
                        "paper": citing_paper_name,
                        "citations": [],
                        "errors": ["未检测到引用片段"]
                    })
                    continue
            
            for snippet_idx, snippet in enumerate(snippets, 1):
                logger.info(
                    "[minimal] 处理 Snippet %d/%d - Citation_%s",
                    snippet_idx,
                    len(snippets),
                    citation_id,
                )
                
                try:
                    # 构建只包含当前 snippet 的用户消息
                    user_message = f"""请分析引用 Citation_{citation_id} 的 Snippet {snippet_idx}。

论文信息：
- Citation ID: {citation_id}
- Citing Paper: {citing_paper_name}
- Cited Paper: {paper_info.citation()}
- Approach Names: {approach_names_str}
- Paper Info JSON: {paper_info_json}

定位结果（已通过工具获取）：
- Reference Number: {reference_number}
- Snippet Index: {snippet_idx}
- Snippet: {json.dumps(snippet, ensure_ascii=False, default=str)}"""
                    
                    # 直接调用 LLM（不使用 agent）
                    logger.info(
                        "[minimal] 直接调用 LLM 进行分析 - Citation_%s, Snippet_%d",
                        citation_id,
                        snippet_idx,
                    )
                    messages = [
                        SystemMessage(content=system_prompt),
                        HumanMessage(content=user_message),
                    ]
                    result = llm.invoke(messages)
                    
                    # 提取 LLM 输出
                    llm_output = result.content if hasattr(result, 'content') else str(result)
                    logger.info(
                        "[minimal] LLM Response (长度: %d 字符):\n%s",
                        len(llm_output) if llm_output else 0,
                        llm_output[:500] + "..." if llm_output and len(llm_output) > 500 else llm_output
                    )
                    
                    # 尝试从 LLM 的输出中提取结果
                    try:
                        # 尝试解析为JSON（使用统一的JSON解析函数）
                        output_data = extract_json_from_text(llm_output)
                        
                        if not output_data:
                            logger.warning(
                                "[minimal] 无法从 LLM 输出中提取 JSON - Citation_%s, Snippet_%d",
                                citation_id,
                                snippet_idx,
                            )
                            citation_errors.append(f"Snippet_{snippet_idx}: 无法解析LLM输出")
                            continue
                        
                        # 新格式：output_data 是一个数组
                        if not isinstance(output_data, list):
                            logger.warning(
                                "[minimal] LLM 输出格式错误，期望数组 - Citation_%s, Snippet_%d",
                                citation_id,
                                snippet_idx,
                            )
                            citation_errors.append(f"Snippet_{snippet_idx}: LLM输出格式错误")
                            continue
                        
                        # 查找当前 citation_id 对应的条目
                        snippet_entry = None
                        for entry in output_data:
                            entry_id = entry.get("id")
                            # 支持字符串和整数类型的ID
                            if str(entry_id) == str(citation_id) or entry_id == citation_id:
                                snippet_entry = entry
                                break
                        
                        if not snippet_entry:
                            logger.warning(
                                "[minimal] 未找到 Citation_%s 的条目 - Snippet_%d",
                                citation_id,
                                snippet_idx,
                            )
                            citation_errors.append(f"Snippet_{snippet_idx}: 未找到对应的条目")
                            continue
                        
                        # 提取该 snippet 的分析结果
                        snippet_citations = snippet_entry.get("citations", [])
                        if snippet_citations:
                            # 确保 snippet_index 正确
                            for cit in snippet_citations:
                                cit["snippet_index"] = snippet_idx
                                # 将\n替换为空格，优化显示效果
                                cit['text'] = cit['text'].replace('\n', ' ')
                            citation_citations.extend(snippet_citations)
                        
                        # 提取错误信息（如果有）
                        errors = snippet_entry.get("errors", [])
                        if errors:
                            citation_errors.extend([f"Snippet_{snippet_idx}: {err}" for err in errors])
                        
                        logger.info(
                            "[minimal] Citation_%s, Snippet_%d 处理完成: %d 条引用片段",
                            citation_id,
                            snippet_idx,
                            len(snippet_citations),
                        )
                    except (json.JSONDecodeError, KeyError, TypeError) as exc:
                        logger.warning(
                            "[minimal] 无法解析 LLM 输出 - Citation_%s, Snippet_%d: %s",
                            citation_id,
                            snippet_idx,
                            exc,
                        )
                        citation_errors.append(f"Snippet_{snippet_idx}: 无法解析LLM输出 - {exc}")
                
                except Exception as exc:
                    logger.exception(
                        "[minimal] 处理失败 - Citation_%s, Snippet_%d, 错误: %s",
                        citation_id,
                        snippet_idx,
                        exc,
                    )
                    citation_errors.append(f"Snippet_{snippet_idx}: {exc}")
            
            # 整合该 citation_id 的所有 snippet 结果
            citation_entry = {
                "id": int(citation_id),
                "paper": citing_paper_name,
                "citations": citation_citations,
                "errors": citation_errors if citation_errors else [],
            }
            
            aggregated_entries.append(citation_entry)
            all_errors.extend([f"Citation_{citation_id}: {err}" for err in citation_errors])
            
            logger.info(
                "[minimal] Citation_%s 处理完成: %d 个 snippets, %d 条引用片段",
                citation_id,
                len(snippets),
                len(citation_citations),
            )
        except Exception as exc:
            logger.exception(
                "[minimal] 处理失败 - Citation_%s, Paper: %s, 错误: %s",
                citation_id,
                paper_id,
                exc,
            )
            all_errors.append(f"Citation_{citation_id}: {exc}")
            aggregated_entries.append({
                "id": int(citation_id),
                "paper": "",
                "citations": [],
                "errors": [str(exc)]
            })

    # 构建报告（使用新格式）
    logger.info("=" * 60)
    logger.info("汇总结果")
    logger.info("=" * 60)
    
    # 统计总引用片段数
    total_citations = sum(len(entry.get("citations", [])) for entry in aggregated_entries)
    logger.info("总引用条目数: %d", len(aggregated_entries))
    logger.info("总引用片段数: %d", total_citations)
    logger.info("总错误数: %d", len(all_errors))   

    return aggregated_entries


def run_supervisor_analysis(
    paper_id: str,
    citation_ids: Optional[List[int]] = None,
    original_paper_path: Optional[str] = None,
    write_output: bool = True,
    chunk_size: int = 1600,
    chunk_overlap: int = 250,
) -> Dict[str, Any]:
    """
    使用 Supervisor Agent 模式运行分析。
    
    Supervisor agent 会自主决定：
    - 如何调用 citation_analysis_agent 和 sentiment_analysis_agent
    - 调用顺序和策略
    - 如何整合结果
    
    Args:
        paper_id: 论文ID（目录路径）
        citation_ids: 要分析的引用ID列表，如果为None则自动发现
        original_paper_path: 原论文路径
        write_output: 是否写入输出文件
        chunk_size: 章节切分大小
        chunk_overlap: 章节重叠大小
    
    Returns:
        分析报告字典
    """
    logger.info("=" * 60)
    logger.info("开始 Supervisor Agent 分析工作流")
    logger.info("=" * 60)
    
    paper_path = Path(paper_id)
    if not paper_path.exists():
        raise FileNotFoundError(f"{paper_id} does not exist.")

    logger.info("加载论文信息: %s", paper_id)
    # 加载论文信息
    paper_info = load_paper_info(str(paper_path))
    logger.info("论文信息: %s", paper_info.citation())
    
    primary_text, primary_source = load_primary_text(paper_path, original_paper_path)
    logger.debug("原论文文本长度: %d 字符", len(primary_text) if primary_text else 0)
    
    paper_sections = (
        build_sections(primary_text, primary_source, chunk_size, chunk_overlap)
        if primary_text
        else None
    )
    logger.info("构建了 %d 个章节", len(paper_sections) if paper_sections else 0)

    # 确定要分析的引用ID
    target_ids = citation_ids or discover_citation_ids(paper_path)
    logger.info("发现 %d 个引用ID: %s", len(target_ids), target_ids)
    
    # 准备 paper_info JSON（供 agents 使用）
    paper_info_json = json.dumps({
        "scholar_id": paper_info.scholar_id,
        "authors": paper_info.authors,
        "approach_name": paper_info.approach_name,
        "title": paper_info.title,
        "venue": paper_info.venue,
        "year": paper_info.year,
    }, ensure_ascii=False)

    # 准备 paper_sections JSON（如果有）
    paper_sections_json = None
    if paper_sections:
        paper_sections_json = json.dumps([
            {
                "section_id": s.section_id,
                "title": s.title,
                "text": s.text,
                "start": s.start,
                "end": s.end,
                "source": s.source,
            }
            for s in paper_sections
        ], ensure_ascii=False, default=str)

    # 创建 supervisor agent
    logger.info("创建 Supervisor Agent...")
    supervisor = create_supervisor_agent()
    logger.info("Supervisor Agent 创建完成")

    # 使用 supervisor agent 处理每个引用
    aggregated_entries: List[Dict[str, Any]] = []
    all_errors: List[str] = []

    logger.info("开始处理 %d 个引用", len(target_ids))
    for idx, citation_id in enumerate(target_ids, 1):
        logger.info("-" * 60)
        logger.info("处理引用 %d/%d: Citation_%s", idx, len(target_ids), citation_id)
        logger.info("-" * 60)
        
        try:
            # 使用 prompt.py 中的函数构建用户消息
            user_message = get_supervisor_user_message(
                citation_id=citation_id,
                paper_path=str(paper_path),
                citing_paper_name=get_citing_paper_name(paper_id, citation_id),
                paper_citation=paper_info.citation(),
                approach_names=paper_info.approach_name,
                paper_info_json=paper_info_json,
                paper_sections_json=paper_sections_json,
            )
            
            logger.info("[supervisor] 用户消息: %s", user_message)
            # 使用 supervisor agent 处理
            logger.info("[supervisor] 使用 Supervisor Agent 处理 Citation_%s", citation_id)
            from langchain_core.messages import HumanMessage
            result = supervisor.invoke({
                "messages": [HumanMessage(content=user_message)]
            })
            
            # 从 messages 中提取最后一条消息的内容
            messages = result.get("messages", [])
            supervisor_output = ""
            if messages:
                last_message = messages[-1]
                supervisor_output = last_message.content if hasattr(last_message, 'content') else str(last_message)
                # 输出大模型的 response
                logger.info("[LLM Response] Supervisor Agent Response (长度: %d 字符):\n%s", 
                           len(supervisor_output) if supervisor_output else 0, 
                           supervisor_output[:500] + "..." if supervisor_output and len(supervisor_output) > 500 else supervisor_output)
            
            # 尝试从 supervisor 的输出中提取结果
            # Supervisor 返回格式为数组，每个元素对应一个引用ID
            try:
                # 尝试解析为JSON（使用统一的JSON解析函数）
                output_data = extract_json_from_text(supervisor_output)
                
                if not output_data:
                    logger.warning("[supervisor] 无法从 supervisor 输出中提取 JSON - Citation_%s", citation_id)
                    all_errors.append(f"Citation_{citation_id}: 无法解析supervisor输出")
                    # 创建错误条目
                    aggregated_entries.append({
                        "id": str(citation_id),
                        "paper": "",
                        "citations": [],
                        "errors": [f"无法解析supervisor输出"]
                    })
                    continue
                
                # 新格式：output_data 是一个数组
                if not isinstance(output_data, list):
                    logger.warning("[supervisor] Supervisor 输出格式错误，期望数组 - Citation_%s", citation_id)
                    all_errors.append(f"Citation_{citation_id}: Supervisor输出格式错误")
                    aggregated_entries.append({
                        "id": str(citation_id),
                        "paper": "",
                        "citations": [],
                        "errors": [f"Supervisor输出格式错误"]
                    })
                    continue
                
                # 查找当前 citation_id 对应的条目
                citation_entry = None
                for entry in output_data:
                    entry_id = entry.get("id")
                    # 支持字符串和整数类型的ID
                    if str(entry_id) == str(citation_id) or entry_id == citation_id:
                        citation_entry = entry
                        break
                
                if not citation_entry:
                    logger.warning("[supervisor] 未找到 Citation_%s 的条目", citation_id)
                    all_errors.append(f"Citation_{citation_id}: 未找到对应的条目")
                    aggregated_entries.append({
                        "id": str(citation_id),
                        "paper": "",
                        "citations": [],
                        "errors": [f"未找到对应的条目"]
                    })
                    continue
                
                # 确保 id 字段是字符串类型
                citation_entry["id"] = str(citation_id)
                
                # 提取错误信息（如果有）
                errors = citation_entry.get("errors", [])
                if errors:
                    all_errors.extend([f"Citation_{citation_id}: {err}" for err in errors])
                
                # 直接使用新格式的条目
                aggregated_entries.append(citation_entry)
                
                citations_count = len(citation_entry.get("citations", []))
                logger.info(
                    "[supervisor] Citation_%s 处理完成: %d 条引用片段",
                    citation_id,
                    citations_count,
                )
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                logger.warning("[supervisor] 无法解析 supervisor 输出 - Citation_%s: %s", citation_id, exc)
                all_errors.append(f"Citation_{citation_id}: 无法解析supervisor输出 - {exc}")
                aggregated_entries.append({
                    "id": str(citation_id),
                    "paper": "",
                    "citations": [],
                    "errors": [f"无法解析supervisor输出: {exc}"]
                })
        except Exception as exc:
            logger.exception(
                "[supervisor] 处理失败 - Citation_%s, Paper: %s, 错误: %s",
                citation_id,
                paper_id,
                exc,
            )
            all_errors.append(f"Citation_{citation_id}: {exc}")
            aggregated_entries.append({
                "id": str(citation_id),
                "paper": "",
                "citations": [],
                "errors": [str(exc)]
            })

    # 构建报告（使用新格式）
    logger.info("=" * 60)
    logger.info("汇总结果")
    logger.info("=" * 60)
    
    # 统计总引用片段数
    total_citations = sum(len(entry.get("citations", [])) for entry in aggregated_entries)
    logger.info("总引用条目数: %d", len(aggregated_entries))
    logger.info("总引用片段数: %d", total_citations)
    logger.info("总错误数: %d", len(all_errors))
    
    return aggregated_entries


def run_summarize(
    analysis_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    总结分析结果，使用 LLM 对所有分析结果进行总结
    
    Args:
        analysis_results: 分析结果列表，每个元素包含 id, paper, citations 等字段
    
    Returns:
        总结结果字典，包含 summary 字段
    """
    logger.info("=" * 60)
    logger.info("开始总结分析结果")
    logger.info("=" * 60)
    
    if not analysis_results:
        logger.warning("分析结果为空，跳过总结")
        return {"summary": "无分析结果可供总结。"}
    
    # 获取 LLM 实例
    from .utils import get_llm, get_llm_config
    from langchain_core.messages import HumanMessage, SystemMessage
    
    config = get_llm_config()
    logger.info(
        "[summarize] 创建 LLM - Model: %s, Base URL: %s",
        config.model,
        config.base_url,
    )
    llm = get_llm(config)
    
    # 构建总结 prompt
    system_prompt = """你是一个学术引用分析专家。你的任务是对所有引用分析结果进行总结，生成一个全面的引用概览。

你需要分析所有引用数据，总结以下方面：
1. **引用范围**：被引论文在哪些研究领域、会议、数据集或研究方向中被引用
2. **学术影响**：被引论文在学术领域的影响力和贡献，举2～3个例子（若有），如：“A论文赞扬被引论文为X领域先驱之作”，或“B论文高度肯定了被引论文的Y贡献”（给出具体论文名称）
3. **情感评估**：正面、中立、负面引用的分布和具体评价内容

请返回一段完整的文本总结，涵盖引用范围、学术影响和情感评估。不要超过5句话。"""
    
    # 准备分析结果数据（转换为JSON字符串）
    analysis_results_json = json.dumps(analysis_results, ensure_ascii=False, indent=2)
    
    user_message = f"""请对以下所有引用分析结果进行总结：

分析结果数据：
{analysis_results_json}"""
    
    # 调用 LLM 进行总结
    logger.info("[summarize] 调用 LLM 进行总结...")
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    result = llm.invoke(messages)
    
    # 提取 LLM 输出
    llm_output = result.content if hasattr(result, 'content') else str(result)
    logger.info(
        "[summarize] LLM Response (长度: %d 字符):\n%s",
        len(llm_output) if llm_output else 0,
        llm_output[:500] + "..." if llm_output and len(llm_output) > 500 else llm_output
    )
    
    # 解析总结结果
    try:
        logger.info("[summarize] 总结完成")
        return {
            "summary": llm_output.strip()
        }
    except Exception as exc:
        return {
            "summary": f"总结生成失败: {exc}"
        }
