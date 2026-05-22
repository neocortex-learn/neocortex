"""Read service: deep-note generation from a URL.

Long-running (30s–3min) async pipeline that mirrors ``cmd_read`` core flow
without the CLI's interactive outline confirmation / feedback / reflection
loops. Suitable for HTTP wrap (POST /api/read) and future WebSocket
progress streaming.

Out of scope (CLI-only):
    - interactive outline confirmation (always runs auto-deep)
    - post-read feedback prompts
    - reflection write-back
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

from neocortex.models import (
    AppConfig,
    Language,
    Profile,
    ReadResult,
)


async def read_url(
    source: str,
    *,
    notes_dir: Path,
    cfg: AppConfig,
    profile: Profile,
    lang: Language,
    focus: str | None = None,
) -> ReadResult:
    """Fetch URL → generate outline → write deep note → return ReadResult."""
    from neocortex.cmd_read import _resolve_topic_dir
    from neocortex.config import get_data_dir
    from neocortex.llm import create_provider
    from neocortex.reader.fetcher import ContentFetcher
    from neocortex.reader.teacher import generate_notes, generate_outline
    from neocortex.search import NoteIndex

    started = time.monotonic()

    if not (cfg.provider and cfg.api_key):
        return ReadResult(
            saved_path="", title="", source=source, topic_dir="",
            aborted=True,
            abort_reason="LLM provider / api_key 未配置；运行 neocortex profile config",
        )

    try:
        provider = create_provider(cfg)
    except Exception as exc:
        return ReadResult(
            saved_path="", title="", source=source, topic_dir="",
            aborted=True,
            abort_reason=f"create_provider 失败: {exc}",
        )

    # Fetch (URL → PDF → EPUB → image → audio all handled by ContentFetcher).
    fetcher = ContentFetcher(provider=provider)
    try:
        doc = await fetcher.fetch(source)
    except Exception as exc:
        return ReadResult(
            saved_path="", title="", source=source, topic_dir="",
            aborted=True,
            abort_reason=f"抓取失败: {exc}",
        )

    # Outline (one LLM call) — service path always auto-deeps everything;
    # interactive c/r prompt belongs in CLI layer.
    try:
        outline = await generate_outline(doc, profile, provider)
    except Exception as exc:
        return ReadResult(
            saved_path="", title=doc.title, source=doc.source, topic_dir="",
            aborted=True,
            abort_reason=f"大纲生成失败: {exc}",
        )

    # Notes (N LLM calls, one per chunk + mindmap header).
    try:
        notes_content = await generate_notes(doc, outline, profile, provider, focus=focus)
    except Exception as exc:
        return ReadResult(
            saved_path="", title=doc.title, source=doc.source, topic_dir="",
            aborted=True,
            abort_reason=f"笔记生成失败: {exc}",
        )

    # Save (same scheme as cmd_read for cross-tool consistency).
    topic_dir = _resolve_topic_dir(notes_dir, doc, outline, profile)
    topic_dir.mkdir(parents=True, exist_ok=True)

    safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in doc.title)
    safe_title = safe_title.strip().replace(" ", "-").lower()[:60] or "note"
    today_str = date.today().isoformat()
    filename = f"{safe_title}-{today_str}.md"
    note_path = topic_dir / filename
    counter = 1
    while note_path.exists():
        counter += 1
        filename = f"{safe_title}-{today_str}-{counter}.md"
        note_path = topic_dir / filename

    deep_topics = [item.title for item in outline.items if item.marker == "deep" and item.title]
    brief_topics = [item.title for item in outline.items if item.marker == "brief" and item.title]
    frontmatter_lines = [
        "---",
        f"title: \"{doc.title.replace(chr(34), chr(39))}\"",
        f"source: \"{doc.source.replace(chr(34), chr(39))}\"",
        f"date: {today_str}",
    ]
    if deep_topics:
        frontmatter_lines.append("tags:")
        for dt in deep_topics[:5]:
            safe_tag = dt.strip().replace(" ", "-").lower()[:30]
            if safe_tag:
                frontmatter_lines.append(f"  - {safe_tag}")
    frontmatter_lines.append("---")
    frontmatter_lines.append("")

    full_content = "\n".join(frontmatter_lines) + notes_content
    note_path.write_text(full_content, encoding="utf-8")

    # Index — best effort (CLI does the same).
    try:
        idx = NoteIndex(get_data_dir() / "neocortex.sqlite")
        rel = str(note_path.relative_to(notes_dir))
        idx.index_note(rel, doc.title, full_content)
    except Exception:
        pass

    # Activity log so the timeline reflects GUI-triggered reads too.
    try:
        from neocortex.config import append_log
        append_log("read", doc.title)
    except Exception:
        pass

    return ReadResult(
        saved_path=str(note_path),
        title=doc.title,
        source=doc.source,
        topic_dir=str(topic_dir.relative_to(notes_dir)) if topic_dir.is_relative_to(notes_dir) else str(topic_dir),
        word_count=len(notes_content.split()),
        deep_topics=deep_topics,
        brief_topics=brief_topics,
        elapsed_seconds=round(time.monotonic() - started, 2),
    )
