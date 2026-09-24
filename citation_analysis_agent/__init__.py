"""
Agent package for citation analysis.
完全基于 LangChain 框架实现。
"""

# Expose key functions for convenience
from .agent.workflows import (  # noqa: F401
    run_supervisor_analysis,
)
from .agent.agents import (  # noqa: F401
    create_citation_analysis_agent,
    create_sentiment_analysis_agent,
    create_supervisor_agent,
)

__all__ = [
    "run_supervisor_analysis",
    "create_citation_analysis_agent",
    "create_sentiment_analysis_agent",
    "create_supervisor_agent",
]

