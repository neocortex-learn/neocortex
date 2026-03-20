"""Claude export directory/file parser."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from neocortex.importer.chatgpt import MIN_MESSAGE_LENGTH, ParsedMessage


def _iso_to_timestamp(iso_str: str) -> float:
    """Convert ISO-8601 datetime string to UNIX timestamp."""
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return dt.timestamp()


def parse_claude_export(path: str) -> list[ParsedMessage]:
    """Parse Claude export conversations.json, extracting only user messages.

    *path* can be either a directory (the Claude export root) or the
    conversations.json file itself.  Filters out messages shorter than
    MIN_MESSAGE_LENGTH characters.
    """
    p = Path(path)
    if p.is_dir():
        json_path = p / "conversations.json"
    else:
        json_path = p

    raw = json_path.read_text(encoding="utf-8")
    conversations: list[dict] = json.loads(raw)

    messages: list[ParsedMessage] = []

    for conv in conversations:
        title = conv.get("name", "")
        conv_created = conv.get("created_at", "")
        chat_messages = conv.get("chat_messages", [])

        for msg in chat_messages:
            if msg.get("sender") != "human":
                continue

            text = (msg.get("text") or "").strip()
            if len(text) < MIN_MESSAGE_LENGTH:
                continue

            msg_created = msg.get("created_at", "")
            try:
                timestamp = _iso_to_timestamp(msg_created) if msg_created else (
                    _iso_to_timestamp(conv_created) if conv_created else 0.0
                )
            except (ValueError, OSError):
                timestamp = 0.0

            messages.append(ParsedMessage(
                content=text,
                timestamp=timestamp,
                conversation_title=title,
            ))

    return messages
