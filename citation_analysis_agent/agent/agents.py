"""
Agents：LangChain Agents 定义
使用官方接口创建和管理agents

根据LangChain最佳实践：
- 使用 create_agent 创建agent（基于LangGraph）
- LLM分析直接在agent的prompt中进行，不使用工具
- 使用 messages state 进行输入输出
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

# 导入共享模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from .prompt import (
    get_citation_analysis_system_prompt,
    get_sentiment_analysis_system_prompt,
    SUPERVISOR_SYSTEM_PROMPT,
)
from .tools import (
    extract_snippet_features,
    locate_citations_tool,
    map_sections_tool,
    prepare_text_for_analysis,
)
from .utils import get_llm, get_llm_config

logger = logging.getLogger(__name__)


def create_citation_analysis_agent():
    """
    创建引用分析agent。
    
    使用LangChain官方接口 create_agent 创建agent（基于LangGraph）。
    该agent负责：
    1. 定位引用片段（使用工具）
    2. 分类引用片段（使用LLM直接分析，不通过工具）
    3. 映射片段到章节（使用工具）
    
    Returns:
        LangGraph agent实例（可直接调用invoke）
    """
    config = get_llm_config()
    logger.info(
        "[agents] 创建引用分析 Agent - Model: %s, Base URL: %s",
        config.model,
        config.base_url,
    )
    
    llm = get_llm(config)
    
    # 工具列表：只包含不涉及LLM的工具
    tools = [
        locate_citations_tool,
        extract_snippet_features,
        map_sections_tool,
    ]
    
    # 从 prompt.py 获取 system prompt
    system_prompt = get_citation_analysis_system_prompt()
    
    # 使用官方接口 create_agent 创建agent
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
    )
    
    return agent


def create_sentiment_analysis_agent():
    """
    创建情感分析agent。
    
    使用LangChain官方接口 create_agent 创建agent（基于LangGraph）。
    该agent负责：
    1. 定位引用片段（使用工具）
    2. 分析情感（使用LLM直接分析，不通过工具）
    3. 映射片段到章节（使用工具）
    
    Returns:
        LangGraph agent实例（可直接调用invoke）
    """
    config = get_llm_config()
    logger.info(
        "[agents] 创建情感分析 Agent - Model: %s, Base URL: %s",
        config.model,
        config.base_url,
    )
    
    llm = get_llm(config)
    
    # 工具列表：只包含不涉及LLM的工具
    tools = [
        locate_citations_tool,
        prepare_text_for_analysis,
        map_sections_tool,
    ]
    
    # 从 prompt.py 获取 system prompt
    system_prompt = get_sentiment_analysis_system_prompt()
    
    # 使用官方接口 create_agent 创建agent
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
    )
    
    return agent


def create_supervisor_agent():
    """
    创建supervisor agent，协调citation和sentiment分析agents。
    
    使用Tool Calling模式，将citation_agent和sentiment_agent作为tools。
    这样supervisor可以自主决定何时调用哪个agent。
    
    Returns:
        LangGraph agent实例（可直接调用invoke）
    """
    config = get_llm_config()
    logger.info(
        "[agents] 创建 Supervisor Agent - Model: %s, Base URL: %s",
        config.model,
        config.base_url,
    )
    
    llm = get_llm(config)
    
    # 创建子agents
    citation_agent = create_citation_analysis_agent()
    sentiment_agent = create_sentiment_analysis_agent()
    
    # 将agents包装为tools，使用StructuredTool确保类型安全
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field
    
    def call_citation_agent_impl(query: str) -> str:
        """
        调用引用分析agent。
        
        Args:
            query: 包含paper_id, citation_id, paper_info_json等信息的JSON字符串或自然语言描述
        
        Returns:
            引用分析结果的JSON字符串
        """
        try:
            logger.info("[Supervisor] 调用引用分析agent: %s", query)
            # 使用新的 messages 格式调用 agent
            result = citation_agent.invoke({
                "messages": [HumanMessage(content=query)]
            })
            # 从 messages 中提取最后一条消息的内容
            messages = result.get("messages", [])
            if messages:
                last_message = messages[-1]
                output = last_message.content if hasattr(last_message, 'content') else str(last_message)
                # 输出大模型的 response
                logger.info("[LLM Response] Citation Analysis Agent Response (长度: %d 字符):\n%s", 
                           len(output) if output else 0, 
                           output[:500] + "..." if output and len(output) > 500 else output)
                return output if output else json.dumps({"error": "No output from agent"}, ensure_ascii=False)
            return json.dumps({"error": "No output from agent"}, ensure_ascii=False)
        except Exception as exc:
            logger.exception(f"引用分析agent调用失败: {exc}")
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
    
    def call_sentiment_agent_impl(query: str) -> str:
        """
        调用情感分析agent。
        
        Args:
            query: 包含paper_id, citation_id, paper_info_json, snippets等信息的JSON字符串或自然语言描述
        
        Returns:
            情感分析结果的JSON字符串
        """
        try:
            logger.info("[Supervisor] 调用情感分析agent: %s", query)
            # 使用新的 messages 格式调用 agent
            result = sentiment_agent.invoke({
                "messages": [HumanMessage(content=query)]
            })
            # 从 messages 中提取最后一条消息的内容
            messages = result.get("messages", [])
            if messages:
                last_message = messages[-1]
                output = last_message.content if hasattr(last_message, 'content') else str(last_message)
                # 输出大模型的 response
                logger.info("[LLM Response] Sentiment Analysis Agent Response (长度: %d 字符):\n%s", 
                           len(output) if output else 0, 
                           output[:500] + "..." if output and len(output) > 500 else output)
                return output if output else json.dumps({"error": "No output from agent"}, ensure_ascii=False)
            return json.dumps({"error": "No output from agent"}, ensure_ascii=False)
        except Exception as exc:
            logger.exception(f"情感分析agent调用失败: {exc}")
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
    
    class AgentQueryInput(BaseModel):
        """Agent查询输入"""
        query: str = Field(..., description="查询内容，可以是JSON字符串或自然语言描述")
    
    call_citation_agent_tool = StructuredTool.from_function(
        func=call_citation_agent_impl,
        name="citation_analysis_agent",
        description="调用引用分析agent。输入应该是包含paper_id, citation_id, paper_info_json等信息的查询。",
        args_schema=AgentQueryInput,
    )
    
    call_sentiment_agent_tool = StructuredTool.from_function(
        func=call_sentiment_agent_impl,
        name="sentiment_analysis_agent",
        description="调用情感分析agent。输入应该是包含paper_id, citation_id, paper_info_json, snippets等信息的查询。",
        args_schema=AgentQueryInput,
    )
    
    tools = [call_citation_agent_tool, call_sentiment_agent_tool]
    
    # 从 prompt.py 获取 supervisor system prompt
    system_prompt = SUPERVISOR_SYSTEM_PROMPT
    
    # 使用官方接口 create_agent 创建agent
    supervisor = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
    )
    
    return supervisor
