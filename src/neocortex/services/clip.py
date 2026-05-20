"""Clip service: console-free entry point for HTTP / GUI / programmatic use.

Mirrors ``neocortex.cmd_clip._run`` core flow (fetch → resolve LLM intent →
process → save → cluster → related → ClipResult) without any Rich/Typer/
interactive prompts. Reuses helpers from ``cmd_clip`` directly so bug fixes
to ``_link_clip_to_concepts`` / ``_compute_new_or_pending`` /
``_find_related_notes`` automatically flow to both CLI and service.

Out of scope (handled by CLI layer only):
    - clipboard / paste detection
    - image OCR (multi-image, single-image vision)
    - interactive "long article → switch to read" prompt

The server may add these as separate endpoints later if needed.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from pathlib import Path

# Reuse CLI helpers as-is — see module docstring for "C path" rationale.
from neocortex.cmd_clip import (
    _compute_new_or_pending,
    _find_related_notes,
    _link_clip_to_concepts,
)
from neocortex.models import (
    AppConfig,
    Clip,
    ClipResult,
    Language,
    Profile,
)


async def clip_text(
    source: str,
    *,
    process: bool | None = None,
    notes_dir: Path,
    cfg: AppConfig,
    profile: Profile,
    lang: Language,
) -> ClipResult:
    """Capture a single text/URL fragment to the knowledge base.

    Mirrors the cmd_clip._run flow for URL/text sources (no paste/image).
    Returns a ClipResult; on hard fetch failure returns aborted=True with
    abort_reason, the caller (CLI / HTTP handler) renders the rejection.
    """
    from neocortex.clipper import fetch_clip_content, process_clip
    from neocortex.config import append_log, get_data_dir, save_clip
    from neocortex.search import NoteIndex

    fetched = await fetch_clip_content(source)

    # Hard fetch failure → don't save, don't process, return aborted result.
    if fetched.get("_fetch_status") == "failed":
        return ClipResult(
            saved_path="",
            clip=Clip(id="", source=source, content=""),
            llm_status="skipped_user_opt_out",
            aborted=True,
            abort_reason=fetched.get("_fetch_error") or "fetch failed",
        )

    # The HTTP/service path currently supports text and URLs only. The shared
    # fetcher marks local image paths as screenshots with empty content so the
    # CLI can run its vision/OCR branch; without that branch here, saving would
    # create an empty screenshot clip that looks successful to the GUI.
    if fetched.get("_image_path") and not fetched.get("content"):
        return ClipResult(
            saved_path="",
            clip=Clip(id="", source=source, content=""),
            llm_status="skipped_user_opt_out",
            aborted=True,
            abort_reason=(
                "image OCR is not supported by the HTTP service yet; "
                "use the CLI `neocortex clip <image>` path for screenshots"
            ),
        )

    title = fetched["title"]
    content = fetched["content"]
    clip_type = fetched["clip_type"]
    clip_source = fetched["source"]
    weak_fetch = fetched.get("_fetch_quality") == "weak"

    # Resolve effective LLM intent (Q11):
    if process is True:
        user_wants_llm = True
    elif process is False:
        user_wants_llm = False
    else:
        user_wants_llm = cfg.clip_default_process

    llm_status = "skipped_user_opt_out"
    llm_error: str | None = None
    processed: dict = {
        "summary": "",
        "relevance": "",
        "related_concepts": [],
        "auto_tags": [],
        "topic": "general",
    }

    # Weak fetch forces LLM skip (avoid hallucinating on near-empty content).
    if weak_fetch and user_wants_llm:
        user_wants_llm = False
        llm_status = "skipped_weak_fetch"

    if user_wants_llm:
        if not (cfg.provider and cfg.api_key):
            llm_status = "skipped_no_key"
        else:
            try:
                from neocortex.llm import create_provider

                provider = create_provider(cfg)
                processed = await process_clip(
                    content, title, profile, provider, lang,
                    notes_dir=notes_dir,
                )
                llm_status = processed.pop("_llm_status", "ok")
                llm_error = processed.pop("_llm_error", None)
                # If the body is mostly non-Chinese and the user prefers
                # Chinese, run a translation pass and append it so the user
                # can read foreign-language clips without context-switching.
                if lang.value == "zh" and llm_status == "ok":
                    from neocortex.clipper import maybe_translate_to_chinese
                    translation = await maybe_translate_to_chinese(content, provider)
                    if translation:
                        content = (
                            f"{content}\n\n---\n\n## 中文译文\n\n{translation}"
                        )
            except Exception as exc:
                llm_status = "failed"
                llm_error = str(exc) or exc.__class__.__name__

    # Title fallback (problem #4 fix replicated here for service path).
    effective_title = title
    if not effective_title:
        summary = processed.get("summary", "").strip()
        if summary:
            effective_title = summary[:40] + ("…" if len(summary) > 40 else "")
        elif content:
            first_line = content.strip().split("\n", 1)[0]
            effective_title = first_line[:40] + ("…" if len(first_line) > 40 else "")

    today = date.today()
    clip_obj = Clip(
        id=uuid.uuid4().hex[:8],
        source=clip_source,
        content=content,
        title=effective_title,
        clip_type=clip_type,
        auto_tags=processed.get("auto_tags", []),
        related_concepts=processed.get("related_concepts", []),
        status="inbox",
        summary=processed.get("summary", ""),
        relevance=processed.get("relevance", ""),
        priority="",
        topic=processed.get("topic", "general"),
        created_at=today.isoformat(),
        processed_at=today.isoformat() if processed.get("summary") else None,
        next_surface=(today + timedelta(days=3)).isoformat(),
    )

    saved_path = save_clip(notes_dir, clip_obj)

    # Index — best-effort, swallow errors as cmd_clip does.
    try:
        idx = NoteIndex(get_data_dir() / "neocortex.sqlite")
        try:
            rel = str(saved_path.relative_to(notes_dir))
        except ValueError:
            rel = saved_path.name
        idx.index_note(rel, clip_obj.title or source[:50], clip_obj.content)
    except Exception:
        pass

    existing_cluster_delta = []
    new_or_pending_clusters: list[str] = []
    related_notes = []
    if clip_obj.related_concepts:
        existing_cluster_delta = _link_clip_to_concepts(notes_dir, clip_obj)
        new_or_pending_clusters = _compute_new_or_pending(notes_dir, clip_obj.related_concepts)
        related_notes = _find_related_notes(notes_dir, clip_obj, saved_path=saved_path)

    append_log("clip", clip_obj.title or source[:50])

    return ClipResult(
        saved_path=str(saved_path),
        clip=clip_obj,
        llm_status=llm_status,
        llm_error=llm_error,
        existing_cluster_delta=existing_cluster_delta,
        new_or_pending_clusters=new_or_pending_clusters,
        related_notes=related_notes,
    )
