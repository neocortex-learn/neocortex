"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], json_mode: bool = False) -> str:
        """Send a chat request and return the text response."""

    @abstractmethod
    async def describe_image(self, image_data: bytes, media_type: str, prompt: str) -> str:
        """Send an image to the LLM and return a text description."""

    @abstractmethod
    def max_context_tokens(self) -> int:
        """Return the model's max context window in tokens."""

    @abstractmethod
    def name(self) -> str:
        """Return the provider display name."""
