"""Visualization commands: concept map and learning digest."""

from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta
from pathlib import Path

import typer

from neocortex.cli import _get_lang, app, console
from neocortex.i18n import t


def _concept_slug(name: str) -> str:
    """Convert concept name to a Mermaid-safe node ID."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())


def _star_rating(evidence_count: int) -> str:
    if evidence_count >= 3:
        return "\u2605\u2605\u2605"
    if evidence_count >= 1:
        return "\u2605\u2605\u2606"
    return "\u2605\u2606\u2606"


def _node_style(slug: str, evidence_count: int) -> str:
    if evidence_count >= 3:
        return f"    style {slug} fill:#2d5016,color:#fff"
    if evidence_count >= 1:
        return f"    style {slug} fill:#8b6914,color:#fff"
    return f"    style {slug} fill:#555,color:#fff"


@app.command()
def map(
    domain: str = typer.Option(None, help="Filter by domain"),
    around: str = typer.Option(None, help="Show neighborhood of a concept"),
) -> None:
    """Generate a visual concept map (Mermaid)."""
    from neocortex.compiler import collect_all_concepts, match_domain
    from neocortex.config import get_notes_dir, load_profile

    lang = _get_lang()
    prof = load_profile()
    notes_dir = get_notes_dir()
    concepts_dir = notes_dir / "concepts"

    with console.status(f"  {t('map_generating', lang)}"):
        all_concepts = collect_all_concepts(concepts_dir)

    if not all_concepts:
        console.print(f"  {t('map_no_concepts', lang)}")
        return

    known_domains = set()
    for domain_name in prof.skills.domains:
        known_domains.add(domain_name.lower())

    if domain:
        all_concepts = [
            c for c in all_concepts
            if match_domain(c.name, known_domains) == domain.lower()
        ]
        if not all_concepts:
            console.print(f"  {t('map_no_concepts', lang)}")
            return

    if around:
        around_lower = around.lower()
        center = None
        for c in all_concepts:
            if c.name.lower() == around_lower:
                center = c
                break
        if center is None:
            console.print(f"  {t('map_no_concepts', lang)}")
            return
        neighbor_names = {n.lower() for n in center.related_concepts}
        neighbor_names.add(center.name.lower())
        all_concepts = [c for c in all_concepts if c.name.lower() in neighbor_names]

    concept_map = {c.name: c for c in all_concepts}

    lines = ["graph LR"]
    styles = []
    seen_edges: set[tuple[str, str]] = set()

    for c in all_concepts:
        slug = _concept_slug(c.name)
        display = f'{c.name} {_star_rating(c.evidence_count)}'
        safe_display = display.replace('"', "'")
        lines.append(f'    {slug}["{safe_display}"]')
        styles.append(_node_style(slug, c.evidence_count))

    for c in all_concepts:
        src_slug = _concept_slug(c.name)
        for rel_name in c.related_concepts:
            if rel_name in concept_map:
                dst_slug = _concept_slug(rel_name)
                edge_key = tuple(sorted((src_slug, dst_slug)))
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    lines.append(f"    {src_slug} --> {dst_slug}")

    lines.extend(styles)

    mermaid_code = "\n".join(lines)

    filter_label = "none"
    if domain:
        filter_label = f"domain={domain}"
    elif around:
        filter_label = f"around={around}"

    today = date.today().isoformat()
    md_content = (
        f"# {t('map_title', lang)}\n\n"
        f"> Generated: {today} | {len(all_concepts)} concepts | Filter: {filter_label}\n\n"
        f"```mermaid\n{mermaid_code}\n```\n"
    )

    maps_dir = notes_dir / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    output_path = maps_dir / f"concept-map-{today}.md"
    output_path.write_text(md_content, encoding="utf-8")

    console.print()
    console.print(f"  [bold]{t('map_title', lang)}[/bold]")
    console.print()
    if domain or around:
        console.print(f"  [dim]{t('map_filtered', lang, filter=filter_label)}[/dim]")
    from rich.syntax import Syntax
    console.print(Syntax(mermaid_code, "text", theme="monokai", padding=1))
    console.print()
    console.print(f"  [green]{t('map_saved', lang, path=str(output_path))}[/green]")
    console.print()


@app.command()
def digest(
    days: int = typer.Option(7, help="Period in days"),
) -> None:
    """Generate a learning digest for the period."""
    from neocortex.compiler import collect_all_concepts
    from neocortex.config import get_notes_dir, load_config, load_flashcards, load_profile
    from neocortex.converger import gather_recent_notes

    lang = _get_lang()
    cfg = load_config()
    prof = load_profile()
    notes_dir = get_notes_dir()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    today = date.today().isoformat()

    with console.status(f"  {t('digest_generating', lang)}"):
        recent_notes = gather_recent_notes(notes_dir, days=days)
        notes_count = len(recent_notes)

        concepts_dir = notes_dir / "concepts"
        all_concepts = collect_all_concepts(concepts_dir)
        new_concepts = [c for c in all_concepts if c.last_updated >= cutoff]
        updated_concepts = [
            c for c in all_concepts
            if c.last_updated >= cutoff and c.evidence_count > 1
        ]

        insights_dir = notes_dir / "insights"
        insights_count = 0
        if insights_dir.exists():
            for f in insights_dir.glob("*.md"):
                try:
                    mtime = date.fromtimestamp(f.stat().st_mtime).isoformat()
                    if mtime >= cutoff:
                        insights_count += 1
                except OSError:
                    continue

        all_cards = load_flashcards(notes_dir)
        reviewed_cards = sum(1 for c in all_cards if c.review_count > 0)

        from neocortex.decay import knowledge_complexity
        complexity = knowledge_complexity(all_concepts)

    week_num = date.today().isocalendar()[1]
    year = date.today().year

    stats_lines = [
        f"# {t('digest_title', lang)} {year}-W{week_num:02d}\n",
        f"> {t('digest_period', lang, days=str(days))}\n",
        "## Stats",
        f"- Notes: {notes_count} new",
        f"- Concepts: {len(new_concepts)} new, {len(updated_concepts)} updated",
        f"- Insights: {insights_count} saved",
        f"- Reviews: {reviewed_cards} cards reviewed",
        f"- {t('complexity_label', lang)}: {complexity['score']:.1f} ({complexity['concept_count']} concepts \u00d7 {complexity['avg_depth']:.2f} depth \u00d7 {complexity['connectivity']:.2f} connectivity)",
        f"- {t('lint_decaying', lang)}: {len(complexity['decaying'])} concepts below threshold",
    ]

    md_content = "\n".join(stats_lines) + "\n"

    convergence_content = ""
    if recent_notes and cfg.provider:
        try:
            from neocortex.converger import detect_cadence, generate_convergence_report
            from neocortex.llm import create_provider

            provider = create_provider(cfg)
            cadence = detect_cadence(recent_notes)

            async def _gen() -> str:
                return await generate_convergence_report(
                    recent_notes, cadence, prof, provider, lang,
                )

            with console.status(f"  {t('converge_generating', lang)}"):
                convergence_content = asyncio.run(_gen())
        except Exception:
            pass

    if convergence_content:
        md_content += f"\n## Convergence\n\n{convergence_content}\n"

    output_path = notes_dir / f"digest-{today}.md"
    output_path.write_text(md_content, encoding="utf-8")

    console.print()
    console.print(f"  [bold]{t('digest_title', lang)}[/bold]")
    console.print()
    console.print(f"  [dim]{t('digest_period', lang, days=str(days))}[/dim]")
    console.print()

    console.print(f"  Notes:    [cyan]{notes_count}[/cyan] new")
    console.print(f"  Concepts: [cyan]{len(new_concepts)}[/cyan] new, [cyan]{len(updated_concepts)}[/cyan] updated")
    console.print(f"  Insights: [cyan]{insights_count}[/cyan] saved")
    console.print(f"  Reviews:  [cyan]{reviewed_cards}[/cyan] cards reviewed")
    console.print(f"  {t('complexity_label', lang)}: [cyan]{complexity['score']:.1f}[/cyan] ({complexity['concept_count']} \u00d7 {complexity['avg_depth']:.2f} \u00d7 {complexity['connectivity']:.2f})")
    if complexity["decaying"]:
        console.print(f"  {t('lint_decaying', lang)}: [yellow]{len(complexity['decaying'])}[/yellow] concepts below threshold")
    console.print()

    console.print(f"  [green]{t('digest_saved', lang, path=str(output_path))}[/green]")
    console.print()
