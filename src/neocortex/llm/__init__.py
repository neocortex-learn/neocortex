"""LLM adapter layer — unified interface for multiple providers."""

from __future__ import annotations

from neocortex.llm.base import LLMProvider
from neocortex.models import AppConfig, ProviderType

__all__ = ["LLMProvider", "create_provider"]


def create_provider(config: AppConfig) -> LLMProvider:
    """Create an LLM provider instance from app config."""
    if config.provider is None:
        raise ValueError("No LLM provider configured")

    api_key = config.api_key
    if not api_key:
        raise ValueError("No API key configured")

    if config.provider == ProviderType.CLAUDE:
        from neocortex.llm.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=api_key, model=config.model)

    if config.provider == ProviderType.OPENAI:
        from neocortex.llm.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(
            api_key=api_key,
            base_url="https://api.openai.com/v1",
            model=config.model or "gpt-4o",
        )

    if config.provider == ProviderType.GEMINI:
        from neocortex.llm.google import GoogleProvider
        return GoogleProvider(api_key=api_key, model=config.model)

    if config.provider == ProviderType.OPENAI_COMPAT:
        if not config.base_url:
            raise ValueError("base_url is required for openai-compat provider")
        if not config.model:
            raise ValueError("model is required for openai-compat provider")
        from neocortex.llm.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(
            api_key=api_key,
            base_url=config.base_url,
            model=config.model,
        )

    raise ValueError(f"Unknown provider: {config.provider}")
