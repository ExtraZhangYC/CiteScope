"""
数据模型：Pydantic 模型定义和配置类
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class ModelConfig:
    """
    LangChain/OpenAI 客户端配置。
    默认从环境变量读取，也支持 CLI 显式覆盖。
    """

    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    pause_seconds: float = 0.0

    @staticmethod
    def from_env(
        api_key_env: str = "OPENAI_API_KEY",
        base_url_env: str = "OPENAI_BASE_URL",
        model_env: str = "OPENAI_MODEL",
    ) -> "ModelConfig":
        api_key = os.getenv(api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(
                f"API key missing. Set {api_key_env} or pass --api-key when launching the agent."
            )
        base_url = os.getenv(base_url_env, "https://api.openai.com/v1").strip()
        model = os.getenv(model_env, "gpt-4o-mini").strip()
        return ModelConfig(api_key=api_key, base_url=base_url, model=model)

