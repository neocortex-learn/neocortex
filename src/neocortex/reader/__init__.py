"""Reader module — fetch content and generate personalized notes."""

from __future__ import annotations

from neocortex.reader.fetcher import ContentFetcher, Document
from neocortex.reader.teacher import generate_notes, generate_outline

__all__ = [
    "ContentFetcher",
    "Document",
    "generate_notes",
    "generate_outline",
]
