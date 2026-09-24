"""
Agent模块：完全基于 LangChain 框架

使用 LangChain Agents 定义多智能体协作工作流，使用 LangChain 的官方接口。
基于 LangChain v1.0 官方文档的最佳实践。

重构要点：
1. 任何不包含LLM的外部分析流程写为工具
2. 使用官方的接口定义模型和agent（create_openai_tools_agent, AgentExecutor）
3. agent能自主决定工具调用和多agent协作（使用LangGraph）
4. LLM分析直接在agent的prompt中进行，不使用工具
"""
from .agents import (
    create_citation_analysis_agent,
    create_sentiment_analysis_agent,
    create_supervisor_agent,
)
from .tools import (
    extract_snippet_features,
    locate_citations_tool,
    map_sections_tool,
    prepare_text_for_analysis,
)
from .workflows import run_supervisor_analysis

__all__ = [
    # Tools (纯工具，不包含LLM)
    "locate_citations_tool",
    "extract_snippet_features",
    "prepare_text_for_analysis",
    "map_sections_tool",
    # Agents (使用官方接口，LLM分析直接在agent中进行)
    "create_citation_analysis_agent",
    "create_sentiment_analysis_agent",
    "create_supervisor_agent",
    # Workflows
    "run_supervisor_analysis",
]
