"""OpenAI-compatible LLM provider (covers OpenAI, Kimi, DeepSeek, MiniMax, Qwen, GLM, etc.)."""

from __future__ import annotations

import re

from openai import AsyncOpenAI

from neocortex.llm.base import LLMProvider

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)

_CONTEXT_SIZES: dict[str, int] = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4.1": 128_000,
    "gpt-4.1-mini": 128_000,
    "gpt-4.1-nano": 128_000,
    "gpt-4-turbo": 128_000,
    "o1": 200_000,
    "o1-mini": 128_000,
    "o3": 200_000,
    "o3-mini": 200_000,
    "o4-mini": 200_000,
    "moonshot-v1-8k": 8_000,
    "moonshot-v1-32k": 32_000,
    "moonshot-v1-128k": 128_000,
    "deepseek-chat": 64_000,
    "deepseek-reasoner": 64_000,
    "MiniMax-M2.7": 1_000_000,
    "MiniMax-M2.5": 1_000_000,
    "MiniMax-M2.1": 1_000_000,
    "MiniMax-M2": 1_000_000,
    "minimax-pro": 128_000,
    "qwen-turbo": 128_000,
    "qwen-plus": 128_000,
    "qwen-max": 128_000,
    "glm-4": 128_000,
    "glm-4-flash": 128_000,
}

_DEFAULT_CONTEXT = 128_000


def _infer_context_size(model: str) -> int:
    if model in _CONTEXT_SIZES:
        return _CONTEXT_SIZES[model]
    for prefix, size in _CONTEXT_SIZES.items():
        if model.startswith(prefix):
            return size
    return _DEFAULT_CONTEXT


def _provider_label(base_url: str) -> str:
    if "openai.com" in base_url:
        return "OpenAI"
    if "moonshot" in base_url:
        return "Kimi"
    if "deepseek" in base_url:
        return "DeepSeek"
    if "minimax" in base_url:
        return "MiniMax"
    if "dashscope" in base_url or "aliyun" in base_url:
        return "Qwen"
    if "bigmodel" in base_url:
        return "GLM"
    return "OpenAI-compat"


class OpenAICompatProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._base_url = base_url

    async def chat(self, messages: list[dict], json_mode: bool = False) -> str:
        kwargs: dict = {
            "model": self._model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)
        if not response.choices:
            raise ValueError("LLM returned empty response")
        text = response.choices[0].message.content or ""
        text = _THINK_RE.sub("", text).strip()
        return text

    def max_context_tokens(self) -> int:
        return _infer_context_size(self._model)

    def name(self) -> str:
        label = _provider_label(self._base_url)
        return f"{label} ({self._model})"
