from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, TypedDict

from pydantic import BaseModel, Field


class CitationLabel(BaseModel):
    """描述 LLM 输出的结构化结果，包含引用方式/类型及分析说明。"""

    citation_mode: Literal["direct_quote", "indirect_reference", "mixed", "unknown"] = Field(
        ...,
        description="Direct quote uses literal wording, indirect reference paraphrases. Use 'mixed' if both appear.",
    )
    citation_type: Literal["viewpoint", "method", "result", "background", "other"] = Field(
        ...,
        description="Select the dominant intent of the citation.",
    )
    analysis: str = Field(..., description="Explain briefly why the classification was chosen.")
    positive: bool = Field(
        ...,
        description="True if the snippet praises, adopts, or extends the paper; False otherwise.",
    )


@dataclass
class PaperSection:
    """描述原论文中一个切片窗口。"""

    section_id: str
    title: str
    text: str
    start: int
    end: int
    source: Optional[str]


@dataclass
class PaperInfo:
    """论文元数据：作者、题目、会议等。"""

    scholar_id: Optional[str]
    authors: List[str]
    approach_name: List[str]
    title: str
    venue: str
    year: str

    def citation(self) -> str:
        authors_str = ", ".join(self.authors)
        return f"{authors_str}. {self.title}. {self.venue}. {self.year}."

