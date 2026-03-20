"""ChatGPT conversations.json parser."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

MIN_MESSAGE_LENGTH = 10


@dataclass
class ParsedMessage:
    content: str
    timestamp: float
    conversation_title: str


def parse_chatgpt_export(path: str) -> list[ParsedMessage]:
    """Parse ChatGPT conversations.json, extracting only user messages.

    Filters out messages shorter than MIN_MESSAGE_LENGTH characters.
    """
    file_path = Path(path)
    raw = file_path.read_text(encoding="utf-8")
    conversations: list[dict] = json.loads(raw)

    messages: list[ParsedMessage] = []

    for conv in conversations:
        title = conv.get("title", "")
        mapping = conv.get("mapping", {})

        for node in mapping.values():
            msg = node.get("message")
            if msg is None:
                continue

            author = msg.get("author", {})
            if author.get("role") != "user":
                continue

            content_obj = msg.get("content", {})
            parts = content_obj.get("parts", [])
            text = "".join(str(p) for p in parts if isinstance(p, str)).strip()

            if len(text) < MIN_MESSAGE_LENGTH:
                continue

            timestamp = msg.get("create_time") or conv.get("create_time") or 0.0

            messages.append(ParsedMessage(
                content=text,
                timestamp=float(timestamp),
                conversation_title=title,
            ))

    return messages
