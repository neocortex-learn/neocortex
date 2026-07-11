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
    from neocortex.config import load_clips
    from neocortex.services.review import get_review_queue_summary

    today = date.today()
    today_str = today.isoformat()

    all_clips = load_clips(notes_dir)
    surfacing_clips = [
        c for c in all_clips
        if c.status in ("inbox", "reference")
        and c.next_surface
        and c.next_surface <= today_str
    ]

    # Context updates (optional, costly) — only when caller opts in.
    context_updates: list[dict] = [{} for _ in surfacing_clips]
    if with_llm and surfacing_clips and cfg.provider and cfg.api_key:
        context_updates = await _llm_context_updates(
            surfacing_clips, notes_dir, cfg,
        ) or context_updates

    surfacing_items: list[SurfacingItem] = []
    for i, clip in enumerate(surfacing_clips):
        days_ago = 0
        try:
            days_ago = (today - date.fromisoformat(clip.created_at)).days
        except (ValueError, TypeError):
            pass
        upd = context_updates[i] if i < len(context_updates) else {}
        # Best-effort saved_path: vault layout writes clips under
        # clips/{date}-{slug}.md but the in-memory Clip doesn't carry the
        # full path. We rebuild relative to notes_dir so the GUI can open it.
        saved = _guess_clip_path(notes_dir, clip)
        surfacing_items.append(SurfacingItem(
            clip_id=clip.id,
            saved_path=str(saved) if saved else "",
            title=clip.title or "(untitled)",
            summary=clip.summary or "",
            days_ago=days_ago,
            related_concepts=list(clip.related_concepts or []),
            context_update=str(upd.get("context_update", "")),
            absorbed=bool(upd.get("absorbed", False)),
        ))

    # Cluster suggestions: concepts touched by ≥3 inbox clips
    concept_counts: dict[str, int] = {}
    for c in all_clips:
        if c.status not in ("inbox", "reference"):
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
    from neocortex.config import load_clips, save_clip

    clips = load_clips(notes_dir)
    target = next((c for c in clips if c.id == clip_id), None)
    if target is None:
        return None

    today = date.today()
    target.surface_count += 1
    if absorbed:
        next_days = _ABSORBED_DAYS
    elif target.surface_count < len(_SURFACE_INTERVALS):
        next_days = _SURFACE_INTERVALS[target.surface_count]
    else:
        next_days = _OVERFLOW_DAYS
    target.next_surface = (today + timedelta(days=next_days)).isoformat()

    save_clip(notes_dir, target)
    return SurfaceUpdate(
        clip_id=target.id,
        next_surface=target.next_surface,
        surface_count=target.surface_count,
        absorbed=absorbed,
    )


def _guess_clip_path(notes_dir: Path, clip) -> Path | None:
    """Reconstruct the on-disk path for a Clip (id-based filename pattern)."""
    if not clip.id:
        return None
    # save_clip's pattern: clips/{date}-{id8}.md (where id8 = first 8 chars of uuid).
    # Some legacy clips use a slug-based name — fall back to a glob search.
    name = f"{clip.created_at}-{clip.id}.md"
    candidate = notes_dir / "clips" / name
    if candidate.exists():
        return candidate
    for p in (notes_dir / "clips").glob(f"*{clip.id}*.md"):
        return p
    return None


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
