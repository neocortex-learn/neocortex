"""Daily command — knowledge briefing with resurfaced clips and due reviews."""

from __future__ import annotations

import asyncio
import json as json_lib
import re
from datetime import date, timedelta
from pathlib import Path

import typer

from neocortex.cli import _get_lang, app, console
from neocortex.i18n import t

SURFACE_INTERVALS = [3, 7, 14, 30, 60]


@app.command()
def daily() -> None:
    """Your daily knowledge briefing — resurfaced clips + due reviews."""
    from neocortex.config import get_due_flashcards, get_notes_dir, load_clips, save_clip

    lang = _get_lang()
    notes_dir = get_notes_dir()
    today_str = date.today().isoformat()
    all_clips = load_clips(notes_dir)

    surfacing = [
        c for c in all_clips
        if c.status in ("inbox", "reference")
        and c.next_surface
        and c.next_surface <= today_str
    ]

    console.print()
    console.print(f"  [bold]{t('daily_title', lang)}[/bold]")
    console.print("  " + "\u2501" * 40)
    console.print()

    if not surfacing:
        console.print(f"  {t('daily_empty', lang)}")
    else:
        context_updates = _get_context_updates(surfacing, notes_dir, lang)
        _display_surfacing(surfacing, context_updates, lang)
        _update_surface_schedule(surfacing, context_updates, notes_dir, save_clip)

    due_cards = get_due_flashcards(notes_dir)
    if due_cards:
        console.print(f"  \U0001f0cf {t('daily_flashcards', lang, count=str(len(due_cards)))}")
        console.print("     \u2192 neocortex review")
        console.print()

    _detect_clusters(all_clips, lang)
    _check_uncompiled(notes_dir, lang)
    _show_health_pulse(notes_dir, lang)


def _get_context_updates(surfacing: list, notes_dir, lang) -> list[dict]:
    from neocortex.config import load_config

    cfg = load_config()
    if not cfg.provider or not cfg.api_key:
        return [{"context_update": "", "absorbed": False} for _ in surfacing]

    concept_summary = _build_concept_summary(notes_dir)

    clip_entries = []
    for i, clip in enumerate(surfacing):
        clip_entries.append(
            f"{i}. Title: {clip.title or '(untitled)'} | "
            f"Concepts: {', '.join(clip.related_concepts) or 'none'} | "
            f"Created: {clip.created_at}"
        )

    prompt_text = (
        "The user's knowledge base has these concepts (with evidence_count):\n"
        + (concept_summary or "(no compiled concepts yet)")
        + "\n\nThe following clips are due for resurfacing. "
        "For each, write a one-sentence 'context update' — "
        "what changed in the user's knowledge since they saved this clip? "
        "If the clip's concept now has deep notes (evidence_count >= 3), mark as absorbed.\n\n"
        + "\n".join(clip_entries)
        + "\n\nOutput JSON array: [{\"index\": 0, \"context_update\": \"...\", \"absorbed\": true/false}, ...]"
    )

    async def _run() -> list[dict]:
        from neocortex.llm import create_provider

        try:
            provider = create_provider(cfg)
            raw = await provider.chat(
                [{"role": "user", "content": prompt_text}],
                json_mode=True,
            )
            results = json_lib.loads(raw)
            if isinstance(results, list):
                return results
        except Exception:
            pass
        return []

    try:
        results = asyncio.run(_run())
    except Exception:
        results = []

    updates_map: dict[int, dict] = {}
    for item in results:
        if isinstance(item, dict) and "index" in item:
            updates_map[int(item["index"])] = item

    final = []
    for i in range(len(surfacing)):
        entry = updates_map.get(i, {})
        final.append({
            "context_update": entry.get("context_update", ""),
            "absorbed": bool(entry.get("absorbed", False)),
        })
    return final


def _build_concept_summary(notes_dir) -> str:
    try:
        from neocortex.compiler import collect_all_concepts
        concepts_dir = notes_dir / "concepts"
        entries = collect_all_concepts(concepts_dir)
        if not entries:
            return ""
        lines = []
        for e in sorted(entries, key=lambda x: -x.evidence_count)[:30]:
            lines.append(f"- {e.name} (evidence: {e.evidence_count})")
        return "\n".join(lines)
    except Exception:
        return ""


def _display_surfacing(surfacing: list, context_updates: list[dict], lang) -> None:
    today = date.today()

    for i, clip in enumerate(surfacing):
        days_ago = 0
        try:
            created = date.fromisoformat(clip.created_at)
            days_ago = (today - created).days
        except (ValueError, TypeError):
            pass

        update_info = context_updates[i] if i < len(context_updates) else {}
        context_update = update_info.get("context_update", "")
        absorbed = update_info.get("absorbed", False)

        console.print(f"  \U0001f4cc {t('daily_ago', lang, days=str(days_ago))}: [bold]{clip.title or '(untitled)'}[/bold]")
        if clip.summary:
            console.print(f"     {clip.summary}")
        if context_update:
            console.print(f"     [dim]Update: {context_update}[/dim]")
        if absorbed:
            console.print(f"     [green]{t('daily_absorbed', lang)} \u2713[/green]")
        else:
            console.print(f"     [cyan]{t('daily_suggest_read', lang)} \u2192[/cyan]")
        console.print()


def _update_surface_schedule(
    surfacing: list,
    context_updates: list[dict],
    notes_dir,
    save_clip_fn,
) -> None:
    today = date.today()

    for i, clip in enumerate(surfacing):
        update_info = context_updates[i] if i < len(context_updates) else {}
        absorbed = update_info.get("absorbed", False)

        clip.surface_count += 1

        if absorbed:
            clip.next_surface = (today + timedelta(days=180)).isoformat()
        elif clip.surface_count < len(SURFACE_INTERVALS):
            next_days = SURFACE_INTERVALS[clip.surface_count]
            clip.next_surface = (today + timedelta(days=next_days)).isoformat()
        else:
            clip.next_surface = (today + timedelta(days=90)).isoformat()

        save_clip_fn(notes_dir, clip)


def _detect_clusters(all_clips: list, lang) -> None:
    concept_counts: dict[str, list] = {}
    for clip in all_clips:
        if clip.status in ("inbox", "reference"):
            for concept in clip.related_concepts:
                concept_counts.setdefault(concept, []).append(clip)

    clusters = {k: v for k, v in concept_counts.items() if len(v) >= 3}
    if clusters:
        for concept, clips_in_cluster in clusters.items():
            console.print(
                f"  \U0001f517 {t('daily_cluster', lang, concept=concept, count=str(len(clips_in_cluster)))}"
            )
        console.print("     \u2192 neocortex inbox --synthesize")
        console.print()


def _check_uncompiled(notes_dir, lang) -> None:
    """Detect uncompiled clips/notes and suggest running compile."""
    import json as _json
    from neocortex.config import get_data_dir

    cache_path = get_data_dir() / "compile_cache.json"
    compiled_files: set[str] = set()
    if cache_path.exists():
        try:
            data = _json.loads(cache_path.read_text(encoding="utf-8"))
            compiled_files = set(data.get("files", {}).keys())
        except (OSError, _json.JSONDecodeError, TypeError):
            pass

    # Count md files that haven't been compiled
    uncompiled = 0
    for md_file in notes_dir.rglob("*.md"):
        if any(p in md_file.parts for p in ("concepts", "insights", "diagrams")):
            continue
        if md_file.name in ("INDEX.md", "overview.md", "log.md"):
            continue
        if md_file.name not in compiled_files and str(md_file) not in compiled_files:
            uncompiled += 1

    if uncompiled >= 3:
        console.print(f"  \U0001f4e6 {t('daily_uncompiled', lang, count=str(uncompiled))}")
        console.print("     \u2192 neocortex kb compile")
        console.print()


def _read_report_scores(reports_dir: Path, prefix: str, score_key: str) -> list[tuple[str, int]]:
    """Read (date, score) pairs from report files matching prefix-*.md."""
    if not reports_dir.exists():
        return []
    results: list[tuple[str, int]] = []
    for rp in sorted(reports_dir.glob(f"{prefix}-*.md"), reverse=True):
        try:
            content = rp.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        m = re.search(rf"^{score_key}:\s*(\d+)", content, re.MULTILINE)
        if m:
            date_str = rp.stem.replace(f"{prefix}-", "")
            results.append((date_str, int(m.group(1))))
    return results


def _sparkline(scores: list[int]) -> str:
    """Generate a simple ASCII sparkline from a list of scores."""
    if not scores:
        return ""
    blocks = " ▁▂▃▄▅▆▇█"
    lo, hi = min(scores), max(scores)
    spread = hi - lo if hi > lo else 1
    return "".join(blocks[min(8, int((s - lo) / spread * 8))] for s in scores)


def _show_health_pulse(notes_dir: Path, lang) -> None:
    """Show a compact health pulse: lint score + fidelity trend."""
    reports_dir = notes_dir / "_reports"
    lint_scores = _read_report_scores(reports_dir, "lint", "score")
    verify_scores = _read_report_scores(reports_dir, "verify", "fidelity_score")

    if not lint_scores and not verify_scores:
        console.print(f"  \U0001f3e5 {t('daily_no_lint', lang)}")
        console.print()
        return

    console.print(f"  [bold]{t('daily_health_title', lang)}[/bold]")

    if lint_scores:
        latest_date, latest_score = lint_scores[0]
        if latest_score >= 80:
            style = "green"
        elif latest_score >= 50:
            style = "yellow"
        else:
            style = "red"

        trend_str = ""
        if len(lint_scores) >= 2:
            delta = latest_score - lint_scores[1][1]
            if delta > 0:
                trend_str = f" [green]▲+{delta}[/green]"
            elif delta < 0:
                trend_str = f" [red]▼{delta}[/red]"

        sparkline = ""
        if len(lint_scores) >= 3:
            recent = [s for _, s in reversed(lint_scores[:8])]
            sparkline = f" [dim]{_sparkline(recent)}[/dim]"

        console.print(
            f"  \U0001f3af [{style}]{t('daily_lint_score', lang, score=str(latest_score))}[/{style}]"
            f"{trend_str}{sparkline}"
        )

        # Staleness warning: lint older than 7 days
        try:
            days_ago = (date.today() - date.fromisoformat(latest_date)).days
            if days_ago >= 7:
                console.print(f"     [dim]{t('daily_stale_lint', lang, days=str(days_ago))}[/dim]")
                console.print("     \u2192 neocortex kb lint")
        except ValueError:
            pass

    if verify_scores:
        latest_date, latest_score = verify_scores[0]
        if latest_score >= 80:
            style = "green"
        elif latest_score >= 50:
            style = "yellow"
        else:
            style = "red"

        trend_str = ""
        if len(verify_scores) >= 2:
            delta = latest_score - verify_scores[1][1]
            if delta > 0:
                trend_str = f" [green]▲+{delta}[/green]"
            elif delta < 0:
                trend_str = f" [red]▼{delta}[/red]"

        sparkline = ""
        if len(verify_scores) >= 3:
            recent = [s for _, s in reversed(verify_scores[:8])]
            sparkline = f" [dim]{_sparkline(recent)}[/dim]"

        console.print(
            f"  \U0001f50d [{style}]{t('daily_fidelity_score', lang, score=str(latest_score))}[/{style}]"
            f"{trend_str}{sparkline}"
        )

    console.print()
