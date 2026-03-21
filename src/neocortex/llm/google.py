"""Google Gemini LLM provider."""

from __future__ import annotations

from google import genai
from google.genai import types

from neocortex.llm.base import LLMProvider

_DEFAULT_MODEL = "gemini-2.5-flash"

_CONTEXT_SIZES: dict[str, int] = {
    "gemini-2.5-flash": 1_048_576,
    "gemini-2.5-pro": 1_048_576,
    "gemini-2.0-flash": 1_048_576,
    "gemini-2.0-flash-lite": 1_048_576,
    "gemini-1.5-pro": 2_097_152,
    "gemini-1.5-flash": 1_048_576,
}

_DEFAULT_CONTEXT = 1_048_576


def _convert_messages(messages: list[dict]) -> tuple[str | None, list[types.Content]]:
    system_text: str | None = None
    contents: list[types.Content] = []

    for msg in messages:
        role = msg["role"]
        text = msg["content"]

        if role == "system":
            if system_text is None:
                system_text = text
            else:
                system_text += "\n\n" + text
        elif role == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=text)]))
        elif role == "assistant":
            contents.append(types.Content(role="model", parts=[types.Part(text=text)]))

    return system_text, contents


class GoogleProvider(LLMProvider):
    def __init__(self, api_key: str, model: str | None = None) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model or _DEFAULT_MODEL

    async def chat(self, messages: list[dict], json_mode: bool = False) -> str:
        system_text, contents = _convert_messages(messages)

        config_kwargs: dict = {}
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"

        config = types.GenerateContentConfig(
            system_instruction=system_text,
            **config_kwargs,
        )

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=config,
        )
        if response.text is None:
            raise ValueError("LLM returned empty response")
        return response.text

    async def describe_image(self, image_data: bytes, media_type: str, prompt: str) -> str:
        contents = [
            types.Content(role="user", parts=[
                types.Part(inline_data=types.Blob(mime_type=media_type, data=image_data)),
                types.Part(text=prompt),
            ]),
        ]
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
        )
        if response.text is None:
            raise ValueError("LLM returned empty response")
        return response.text

    def max_context_tokens(self) -> int:
        return _CONTEXT_SIZES.get(self._model, _DEFAULT_CONTEXT)

    def name(self) -> str:
        return f"Google ({self._model})"
