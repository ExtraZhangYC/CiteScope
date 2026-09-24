"""
工具函数：LLM 相关工具和解析函数
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional

from langchain_openai import ChatOpenAI

from .models import ModelConfig

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    从文本中提取JSON对象（统一的JSON解析函数）。
    
    支持多种格式：
    - 直接的JSON字符串
    - 包含在代码块中的JSON（```json ... ```）
    - 包含在文本中的JSON对象
    
    Args:
        text: 包含JSON的文本
    
    Returns:
        解析后的JSON字典，如果解析失败则返回None
    """
    if not text:
        return None
    
    try:
        # 尝试直接解析
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 清理文本
    cleaned = text.strip()
    
    # 移除代码块标记
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.MULTILINE)
    
    # 尝试找到完整的JSON对象（通过括号匹配）
    try:
        start_idx = cleaned.find('[')
        if start_idx >= 0:
            bracket_count = 0
            end_idx = -1
            for i in range(start_idx, len(cleaned)):
                if cleaned[i] == '[':
                    bracket_count += 1
                elif cleaned[i] == ']':
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_idx = i
                        break
            
            if end_idx > start_idx:
                json_str = cleaned[start_idx:end_idx + 1]
                return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        pass
    
    # 如果所有方法都失败，返回None
    logger.warning("[utils] 无法从文本中提取JSON")
    return None


def get_llm(config: Optional[ModelConfig] = None) -> ChatOpenAI:
    """获取配置好的 LLM 实例"""
    if config is None:
        try:
            config = ModelConfig.from_env()
        except RuntimeError:
            config = ModelConfig(
                api_key=os.getenv("OPENAI_API_KEY", ""),
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            )
    
    return ChatOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=0.2,
    )


def get_llm_config() -> ModelConfig:
    """获取 LLM 配置（用于日志输出）"""
    try:
        return ModelConfig.from_env()
    except RuntimeError:
        return ModelConfig(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        )

