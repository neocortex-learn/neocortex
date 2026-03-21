"""Anthropic Claude LLM provider."""

from __future__ import annotations

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock

from neocortex.llm.base import LLMProvider

_DEFAULT_MODEL = "claude-sonnet-4-6"

_CONTEXT_SIZES: dict[str, int] = {
    "claude-sonnet-4-6": 200_000,
    "claude-opus-4-6": 200_000,
    "claude-haiku-3-5": 200_000,
    "claude-sonnet-3-5": 200_000,
    "claude-3-5-sonnet": 200_000,
    "claude-3-5-haiku": 200_000,
    "claude-3-opus": 200_000,
    "claude-3-sonnet": 200_000,
    "claude-3-haiku": 200_000,
}

_DEFAULT_CONTEXT = 200_000

_JSON_SYSTEM_SUFFIX = (
    "\n\nYou MUST respond with valid JSON only. "
    "Do not include any text before or after the JSON object."
)


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str | None = None) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model or _DEFAULT_MODEL

    async def chat(self, messages: list[dict], json_mode: bool = False) -> str:
        system_text = ""
        chat_messages: list[dict] = []

        for msg in messages:
            if msg["role"] == "system":
                if system_text:
                    system_text += "\n\n"
                system_text += msg["content"]
            else:
                chat_messages.append({"role": msg["role"], "content": msg["content"]})

        if json_mode:
            system_text += _JSON_SYSTEM_SUFFIX

        kwargs: dict = {
            "model": self._model,
            "max_tokens": 8192,
            "messages": chat_messages,
        }
        if system_text:
            kwargs["system"] = system_text

        response = await self._client.messages.create(**kwargs)
        for block in response.content:
            if isinstance(block, TextBlock):
                return block.text
        raise ValueError("No text content in LLM response")

    async def describe_image(self, image_data: bytes, media_type: str, prompt: str) -> str:
        import base64

        b64 = base64.b64encode(image_data).decode()
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        for block in response.content:
            if isinstance(block, TextBlock):
                return block.text
        raise ValueError("No text content in LLM response")

    def max_context_tokens(self) -> int:
        return _CONTEXT_SIZES.get(self._model, _DEFAULT_CONTEXT)

    def name(self) -> str:
        return f"Anthropic ({self._model})"
