"""Daily briefing service — pure data version of ``cmd_daily``.

The CLI command prints with Rich and mutates ``next_surface`` schedules in
one shot. This service is read-only: it computes the same 5-section briefing
(surfacing / flashcards / clusters / uncompiled / health pulse) and returns
it as a ``DailyBriefing`` model for HTTP / GUI callers.

LLM context-update enrichment runs only when a provider is configured; otherwise
``SurfacingItem.context_update`` stays empty so the GUI just shows summary +
days-ago. The HTTP path will not block on LLM by default — see ``with_llm``.
"""

from __future__ import annotations

import json as json_lib
from datetime import date
from pathlib import Path

from neocortex.models import (
    AppConfig,
    ClusterSuggestion,
    DailyBriefing,
    HealthPulse,
    Language,
    Profile,
    SurfaceUpdate,
    SurfacingItem,
)

# Spaced-resurfacing schedule (days). Mirrors cmd_daily.SURFACE_INTERVALS;
# kept duplicated here so the service doesn't import cmd_daily (Rich +
# Typer pulled in).
_SURFACE_INTERVALS = [3, 7, 14, 30, 60]
_ABSORBED_DAYS = 180  # clip is mature — push way out
_OVERFLOW_DAYS = 90   # ran out of intervals — repeat quarterly


async def build_briefing(
    *,
    notes_dir: Path,
    cfg: AppConfig,
    profile: Profile,
    lang: Language,
    with_llm: bool = False,
) -> DailyBriefing:
    """Assemble today's briefing.

    ``with_llm=False`` (default) skips the per-clip context-update LLM call
    so the endpoint returns in <100ms even with dozens of surfacing items.
    ``with_llm=True`` triggers one batched LLM call to summarise "what's
    changed" — slower (1–3s), better signal.
    """
    from neocortex.services.review import get_review_queue_summary
    from neocortex.services.inbox import load_stored_clips

    today = date.today()
    today_str = today.isoformat()

    stored_clips = load_stored_clips(notes_dir)
    all_clips = [stored.clip for stored in stored_clips]
    surfacing_stored = [
        stored for stored in stored_clips
        if stored.clip.status == "inbox"
        and stored.clip.next_surface
        and stored.clip.next_surface <= today_str
    ]

    # P0 ordering is deterministic and explainable: an explicit Top of Mind
    # match wins, then the oldest due date, creation date and clip id break ties.
    ranked = [
        (stored, _top_of_mind_reason(stored.clip, cfg.top_of_mind))
        for stored in surfacing_stored
    ]
    ranked.sort(key=lambda pair: _surfacing_sort_key(pair[0].clip, pair[1], cfg.top_of_mind))
    surfacing_total = len(ranked)
    selected = ranked[:3]

    # Context updates (optional, costly) — only when caller opts in.
    selected_clips = [stored.clip for stored, _reason in selected]
    context_updates: list[dict] = [{} for _ in selected_clips]
    if with_llm and selected_clips and cfg.provider and cfg.api_key:
        context_updates = await _llm_context_updates(
            selected_clips, notes_dir, cfg,
        ) or context_updates

    surfacing_items: list[SurfacingItem] = []
    for i, (stored, priority_reason) in enumerate(selected):
        clip = stored.clip
        days_ago = 0
        try:
            days_ago = (today - date.fromisoformat(clip.created_at)).days
        except (ValueError, TypeError):
            pass
        upd = context_updates[i] if i < len(context_updates) else {}
        surfacing_items.append(SurfacingItem(
            clip_id=clip.id,
            saved_path=str(stored.path),
            title=clip.title or "(untitled)",
            summary=clip.summary or "",
            days_ago=days_ago,
            related_concepts=list(clip.related_concepts or []),
            context_update=str(upd.get("context_update", "")),
            absorbed=bool(upd.get("absorbed", False)),
            priority_reason=priority_reason,
        ))

    continue_read = None
    later = [stored for stored in stored_clips if stored.clip.status == "later"]
    later.sort(key=lambda stored: (
        stored.clip.processed_at or stored.clip.created_at,
        stored.clip.created_at,
        stored.clip.id,
    ))
    if later:
        stored = later[0]
        clip = stored.clip
        days_ago = 0
        try:
            days_ago = (today - date.fromisoformat(clip.created_at)).days
        except (ValueError, TypeError):
            pass
        continue_read = SurfacingItem(
            clip_id=clip.id,
            saved_path=str(stored.path),
            title=clip.title or "(untitled)",
            summary=clip.summary or "",
            days_ago=days_ago,
            related_concepts=list(clip.related_concepts or []),
        )

    # Cluster suggestions: concepts touched by ≥3 inbox clips
    concept_counts: dict[str, int] = {}
    for c in all_clips:
        if c.status != "inbox":
            continue
        for concept in c.related_concepts:
            concept_counts[concept] = concept_counts.get(concept, 0) + 1
    cluster_suggestions = [
        ClusterSuggestion(concept=k, clip_count=v)
        for k, v in concept_counts.items() if v >= 3
    ]
    cluster_suggestions.sort(key=lambda x: -x.clip_count)

    # Uncompiled count
    uncompiled = _uncompiled_count(notes_dir)

    # Health pulse
    pulse = _build_health_pulse(notes_dir)

    # Due flashcards：必须来自共享 review service 的唯一实现，保证与
    # POST /api/review/session 的 due_total 在同一快照下相等。
    try:
        due_count = get_review_queue_summary(notes_dir).due_total
    except Exception:
        due_count = 0

    return DailyBriefing(
        date=today_str,
        surfacing=surfacing_items,
        surfacing_total=surfacing_total,
        continue_read=continue_read,
        top_of_mind=list(cfg.top_of_mind),
        due_flashcard_count=due_count,
        cluster_suggestions=cluster_suggestions,
        uncompiled_count=uncompiled,
        health_pulse=pulse,
    )


def mark_surfaced(
    *, notes_dir: Path, clip_id: str, absorbed: bool = False,
) -> SurfaceUpdate | None:
    """Advance a clip's surface schedule. Returns None if no clip matches.

    Mirrors cmd_daily._update_surface_schedule for one clip:
        absorbed=True       → next_surface = today + 180d
        surface_count < 5   → SURFACE_INTERVALS[surface_count]
        otherwise           → +90d (quarterly maintenance)
    """
    from datetime import timedelta
    from neocortex.services.inbox import (
        InboxFlowError,
        find_stored_clip,
        update_clip_frontmatter,
    )

    try:
        stored = find_stored_clip(notes_dir, clip_id)
    except InboxFlowError:
        return None
    target = stored.clip

    today = date.today()
    target.surface_count += 1
    if absorbed:
        next_days = _ABSORBED_DAYS
    elif target.surface_count < len(_SURFACE_INTERVALS):
        next_days = _SURFACE_INTERVALS[target.surface_count]
    else:
        next_days = _OVERFLOW_DAYS
    target.next_surface = (today + timedelta(days=next_days)).isoformat()

    update_clip_frontmatter(stored.path, {
        "next_surface": target.next_surface,
        "surface_count": target.surface_count,
    })
    return SurfaceUpdate(
        clip_id=target.id,
        next_surface=target.next_surface,
        surface_count=target.surface_count,
        absorbed=absorbed,
    )


def _top_of_mind_reason(clip, topics: list[str]) -> str | None:
    """Return the first explicit case-insensitive topic match explanation."""
    import re

    haystacks = [
        clip.title, clip.summary, clip.topic,
        *clip.related_concepts, *clip.auto_tags,
    ]
    normalised = [str(value).casefold() for value in haystacks if value]
    for topic in topics:
        needle = topic.casefold()
        if not needle:
            continue
        # Latin topics use token boundaries so a focus on "AI" does not
        # accidentally boost "daily". CJK topics use direct substring match.
        if needle.isascii():
            pattern = re.compile(rf"(?<![0-9a-z]){re.escape(needle)}(?![0-9a-z])")
            matched = any(pattern.search(value) for value in normalised)
        else:
            matched = any(needle in value for value in normalised)
        if matched:
            return f"Top of Mind: {topic}"
    return None


def _surfacing_sort_key(clip, reason: str | None, topics: list[str]) -> tuple:
    if reason is None:
        topic_rank = len(topics)
    else:
        matched = reason.removeprefix("Top of Mind: ").casefold()
        topic_rank = next(
            (index for index, topic in enumerate(topics) if topic.casefold() == matched),
            len(topics),
        )
    return (
        reason is None,
        topic_rank,
        clip.next_surface or "9999-12-31",
        clip.created_at,
        clip.id,
    )


async def _llm_context_updates(surfacing, notes_dir: Path, cfg: AppConfig) -> list[dict]:
    """One batched LLM call: per-clip 'what's changed' + absorbed flag.

    Mirrors cmd_daily._get_context_updates but as a coroutine the HTTP
    handler can await directly (no nested asyncio.run).
    """
    from neocortex.cmd_daily import _build_concept_summary
    from neocortex.llm import create_provider

    concept_summary = _build_concept_summary(notes_dir)
    entries = [
        f"{i}. Title: {c.title or '(untitled)'} | "
        f"Concepts: {', '.join(c.related_concepts) or 'none'} | "
        f"Created: {c.created_at}"
        for i, c in enumerate(surfacing)
    ]
    prompt = (
        "The user's knowledge base has these concepts (with evidence_count):\n"
        + (concept_summary or "(no compiled concepts yet)")
        + "\n\nThe following clips are due for resurfacing. "
        "For each, write a one-sentence 'context update' — "
        "what changed in the user's knowledge since they saved this clip? "
        "If the clip's concept now has deep notes (evidence_count >= 3), mark as absorbed.\n\n"
        + "\n".join(entries)
        + "\n\nOutput JSON array: [{\"index\": 0, \"context_update\": \"...\", \"absorbed\": true/false}, ...]"
    )
    try:
        provider = create_provider(cfg)
        raw = await provider.chat(
            [{"role": "user", "content": prompt}], json_mode=True,
        )
        results = json_lib.loads(raw)
        if not isinstance(results, list):
            return []
    except Exception:
        return []

    out: list[dict] = [{} for _ in surfacing]
    for item in results:
        if not isinstance(item, dict) or "index" not in item:
            continue
        try:
            idx = int(item["index"])
        except (ValueError, TypeError):
            continue
        if 0 <= idx < len(out):
            out[idx] = item
    return out


def _uncompiled_count(notes_dir: Path) -> int:
    from neocortex.compiler import CompileCache, collect_compilable_notes
    from neocortex.config import get_data_dir

    cache_path = get_data_dir() / "compile_cache.json"
    cache = CompileCache(cache_path, notes_root=notes_dir)
    return sum(cache.is_changed(note) for note in collect_compilable_notes(notes_dir))


def _build_health_pulse(notes_dir: Path) -> HealthPulse:
    from neocortex.cmd_daily import _read_report_scores, _sparkline

    reports_dir = notes_dir / "_reports"
    pulse = HealthPulse()
    if not reports_dir.exists():
        return pulse

    lint = _read_report_scores(reports_dir, "lint", "score")
    if lint:
        pulse.lint_score = lint[0][1]
        if len(lint) >= 2:
            pulse.lint_delta = lint[0][1] - lint[1][1]
        if len(lint) >= 3:
            pulse.lint_sparkline = _sparkline([s for _, s in reversed(lint[:8])])
        try:
            days_ago = (date.today() - date.fromisoformat(lint[0][0])).days
            pulse.lint_stale_days = days_ago
        except ValueError:
            pass

    verify = _read_report_scores(reports_dir, "verify", "fidelity_score")
    if verify:
        pulse.verify_score = verify[0][1]
        if len(verify) >= 2:
            pulse.verify_delta = verify[0][1] - verify[1][1]
        if len(verify) >= 3:
            pulse.verify_sparkline = _sparkline([s for _, s in reversed(verify[:8])])

    return pulse
