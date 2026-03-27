"""Learning-related commands: recommend, plan, growth, converge, opportunities."""

from __future__ import annotations

import asyncio
import json as json_lib
import sys
from datetime import date
from pathlib import Path

import typer
from rich.prompt import Prompt

from neocortex.cli import _get_lang, app, console
from neocortex.i18n import t
from neocortex.models import Language


@app.command()
def recommend(
    count: int = typer.Option(5, help="Number of recommendations"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Get personalized learning recommendations based on your profile."""
    from uuid import uuid4

    from neocortex.config import (
        load_config,
        load_gap_progress,
        load_profile,
        load_recommendations,
        save_recommendations,
    )
    from neocortex.llm import create_provider
    from neocortex.recommender import generate_recommendations, parse_resource
    from neocortex.tracker import expire_stale_recommendations

    cfg = load_config()
    prof = load_profile()
    lang = _get_lang()

    if not prof.skills.languages and not prof.skills.domains:
        console.print(f"  {t('profile_empty', lang)}")
        raise typer.Exit(1)

    try:
        provider = create_provider(cfg)
    except ValueError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
        raise typer.Exit(1)

    # Probe low-confidence skills before recommending
    from neocortex.config import save_profile
    from neocortex.prober import generate_probe, evaluate_response, get_low_confidence_skills, update_skill_confidence

    low_conf = get_low_confidence_skills(prof, threshold=0.5)

    if low_conf and not json_output and sys.stdout.isatty():
        # Pick the most relevant low-confidence skill (first = lowest confidence)
        target = low_conf[0]
        console.print()
        console.print(f"  [bold]{t('probe_intro', lang, skill=target['name'])}[/bold]")

        async def _run_probe() -> dict:
            return await generate_probe(
                target["name"], target["type"], target["level"], prof, provider, lang,
            )

        probe = asyncio.run(_run_probe())

        if probe.get("questions"):
            if probe.get("context"):
                console.print(f"  [dim]{probe['context']}[/dim]")
            console.print()

            for q in probe["questions"]:
                console.print(f"  [bold]?[/bold] {q}")
                answer = Prompt.ask("   ", default="skip", console=console)

                if answer.lower() == "skip":
                    console.print(f"  [dim]{t('probe_skipped', lang)}[/dim]")
                    continue

                async def _run_eval() -> dict:
                    return await evaluate_response(
                        target["name"], q, answer, target["level"], provider, lang,
                    )

                result = asyncio.run(_run_eval())
                delta = result.get("confidence_delta", 0.0)
                new_conf = update_skill_confidence(prof, target["name"], target["type"], delta)

                if result.get("feedback"):
                    console.print(f"  [dim]{result['feedback']}[/dim]")
                console.print(f"  [dim]{t('probe_confidence', lang, skill=target['name'], conf=f'{new_conf:.0%}')}[/dim]")

            save_profile(prof)
            console.print()

    existing_records = load_recommendations()
    existing_records = expire_stale_recommendations(existing_records)
    save_recommendations(existing_records)

    async def _run() -> list:
        with console.status(f"  {t('recommend_generating', lang)}"):
            return await generate_recommendations(prof, provider, count, lang, records=existing_records)

    recs = asyncio.run(_run())

    if not recs:
        console.print(f"  [yellow]{t('recommend_empty', lang)}[/yellow]")
        return

    from neocortex.models import RecommendationRecord

    existing_topics = {r.topic for r in existing_records if r.status == "pending"}
    new_records = []
    for rec in recs:
        if rec.topic in existing_topics:
            continue
        record = RecommendationRecord(
            id=str(uuid4()),
            topic=rec.topic,
            resources=[parse_resource(r) for r in rec.resources],
            related_gaps=rec.related_gaps,
            step=rec.step,
            depends_on=rec.depends_on,
            created_at=date.today().isoformat(),
        )
        new_records.append(record)
        existing_topics.add(rec.topic)

    all_records = existing_records + new_records

    if json_output or not sys.stdout.isatty():
        typer.echo(json_lib.dumps(
            [r.model_dump(mode="json") for r in recs],
            ensure_ascii=False, indent=2,
        ))
        return

    save_recommendations(all_records)

    gap_progress = load_gap_progress()
    total_gaps = len(gap_progress)
    done_gaps = sum(1 for v in gap_progress.values() if v.status in ("learning", "known"))

    console.print()
    console.print(f"  [bold]{t('recommend_path_title', lang)}[/bold]")
    console.print("  " + "\u2501" * 52)

    if total_gaps > 0:
        console.print(f"  [dim]{t('recommend_progress', lang, done=str(done_gaps), total=str(total_gaps))}[/dim]")

    completed = [r for r in existing_records if r.status == "completed"]
    completed_topics = {r.topic for r in existing_records if r.status == "completed"}
    if completed:
        console.print()
        for rec in completed[-3:]:
            console.print(f"  [dim]\u2705 {rec.topic} \u2014 {t('recommend_completed', lang)}[/dim]")

    for i, rec in enumerate(recs, 1):
        is_first = i == 1
        is_last = i == len(recs)
        if is_first:
            connector = "  \u250c\u2500"
        elif is_last:
            connector = "  \u2514\u2500"
        else:
            connector = "  \u251c\u2500"

        is_locked = rec.depends_on and not all(d in completed_topics for d in rec.depends_on)
        step_num = rec.step if hasattr(rec, 'step') and rec.step else i
        if is_locked:
            console.print()
            console.print(f"{connector} [dim]\U0001f512 Step {step_num}: {rec.topic}[/dim]")
            deps_str = ", ".join(rec.depends_on)
            console.print(f"  \u2502  [dim]{t('recommend_locked', lang)} ({deps_str})[/dim]")
            continue
        console.print()
        console.print(f"{connector} [bold cyan]Step {step_num}: {rec.topic}[/bold cyan]")
        if rec.depends_on:
            deps_str = ", ".join(rec.depends_on)
            console.print(f"  \u2502  [dim]{t('recommend_depends_on', lang, deps=deps_str)}[/dim]")
        if rec.related_gaps:
            gaps_str = ", ".join(rec.related_gaps)
            console.print(f"  \u2502  [magenta]{t('recommend_gap_label', lang)}[/magenta] {gaps_str}")
        console.print(f"  \u2502  {rec.reason}")
        if rec.expected_benefit:
            console.print(f"  \u2502  [green]{t('recommend_benefit', lang)}[/green] {rec.expected_benefit}")
        if rec.resources:
            for res in rec.resources:
                console.print(f"  \u2502    [dim]- {res}[/dim]")

    console.print()


@app.command()
def plan(
    weeks: int = typer.Option(4, help="Number of weeks"),
) -> None:
    """Generate a personalized learning plan."""
    from neocortex.config import get_data_dir, get_notes_dir, load_config, load_profile
    from neocortex.llm import create_provider
    from neocortex.planner import generate_plan

    cfg = load_config()
    prof = load_profile()
    lang = cfg.output_settings.language

    if not prof.skills.languages and not prof.skills.domains:
        console.print(f"  {t('profile_empty', lang)}")
        raise typer.Exit(1)

    try:
        provider = create_provider(cfg)
    except ValueError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
        raise typer.Exit(1)

    async def _run() -> str:
        with console.status(f"  {t('plan_generating', lang)}"):
            return await generate_plan(prof, provider, weeks, lang)

    plan_md = asyncio.run(_run())

    today = date.today().isoformat()
    plan_md = plan_md.replace("{date}", today)

    notes_dir = get_notes_dir()
    filename = f"learning-plan-{today}.md"
    plan_path = notes_dir / filename
    counter = 1
    while plan_path.exists():
        counter += 1
        filename = f"learning-plan-{today}-{counter}.md"
        plan_path = notes_dir / filename
    plan_path.write_text(plan_md, encoding="utf-8")

    from neocortex.search import NoteIndex

    note_index = NoteIndex(get_data_dir() / "neocortex.sqlite")
    title = "Personalized Learning Plan" if lang == Language.EN else "\u4e2a\u6027\u5316\u5b66\u4e60\u8ba1\u5212"
    note_index.index_note(plan_path.name, title, plan_md)

    console.print()
    console.print(f"  [green]{t('plan_saved', lang, path=str(plan_path))}[/green]")
    console.print()

    if cfg.output_settings.auto_open:
        import platform
        import subprocess
        opener = "open" if platform.system() == "Darwin" else "xdg-open"
        try:
            subprocess.Popen([opener, str(plan_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


@app.command()
def growth(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show your skill growth over time."""
    from neocortex.config import get_data_dir, load_gap_progress, load_recommendations
    from neocortex.growth import load_snapshots, compute_diff

    lang = _get_lang()
    snapshots = load_snapshots(get_data_dir())

    if len(snapshots) < 1:
        console.print(f"  [yellow]{t('growth_no_data', lang)}[/yellow]")
        return

    if json_output or not sys.stdout.isatty():
        if len(snapshots) >= 2:
            diff = compute_diff(snapshots[0], snapshots[-1])
            typer.echo(json_lib.dumps(diff, ensure_ascii=False, indent=2))
        else:
            typer.echo(json_lib.dumps({"snapshots": 1, "message": "Need at least 2 scans to show growth"}, ensure_ascii=False, indent=2))
        return

    console.print()
    console.print(f"  [bold]{t('growth_title', lang)}[/bold]")
    console.print("  " + "\u2501" * 52)

    latest = snapshots[-1]
    console.print(f"\n  [dim]{t('growth_snapshots', lang, count=str(len(snapshots)))}[/dim]")
    console.print(f"  {t('growth_current', lang)}  [bold]{latest.total_lines:,}[/bold] lines | [bold]{latest.total_projects}[/bold] projects | [bold]{latest.notes_count}[/bold] notes")

    if len(snapshots) >= 2:
        diff = compute_diff(snapshots[0], snapshots[-1])
        console.print(f"\n  [bold]{diff['period']}[/bold]")

        if diff["lines_delta"] > 0:
            console.print(f"  [green]+{diff['lines_delta']:,} lines[/green]")
        if diff["projects_delta"] > 0:
            console.print(f"  [green]+{diff['projects_delta']} projects[/green]")
        if diff["notes_delta"] > 0:
            console.print(f"  [green]+{diff['notes_delta']} notes[/green]")

        if diff["new_languages"]:
            console.print(f"\n  [bold cyan]{t('growth_new_langs', lang)}[/bold cyan]")
            for lang_name in diff["new_languages"]:
                console.print(f"    + {lang_name}")

        if diff["level_ups"]:
            console.print(f"\n  [bold green]{t('growth_level_ups', lang)}[/bold green]")
            for up in diff["level_ups"]:
                console.print(f"    {up['skill']}: {up['from']} \u2192 {up['to']}")

        if diff["new_domains"]:
            console.print(f"\n  [bold cyan]{t('growth_new_domains', lang)}[/bold cyan]")
            for d in diff["new_domains"]:
                console.print(f"    + {d}")

        if diff["gaps_closed"]:
            console.print(f"\n  [bold green]{t('growth_gaps_closed', lang)}[/bold green]")
            for g in diff["gaps_closed"]:
                console.print(f"    \u2713 {g}")

    rec_records = load_recommendations()
    gap_progress = load_gap_progress()

    if rec_records or gap_progress:
        console.print()
        console.print(f"  [bold]{t('growth_rec_title', lang)}[/bold]")
        console.print("  " + "\u2501" * 52)

        if rec_records:
            completed = sum(1 for r in rec_records if r.status == "completed")
            skipped = sum(1 for r in rec_records if r.status == "skipped")
            total = sum(1 for r in rec_records if r.status in ("pending", "completed"))
            if total > 0:
                rate = round(completed / total * 100)
                console.print(f"  {t('growth_rec_completed', lang)} [bold]{completed}[/bold]")
                console.print(f"  {t('growth_rec_rate', lang, rate=str(rate))}")
            if skipped > 0:
                console.print(f"  [dim]{t('recommend_skipped', lang)}: {skipped}[/dim]")

        if gap_progress:
            learning = [k for k, v in gap_progress.items() if v.status == "learning"]
            known = [k for k, v in gap_progress.items() if v.status == "known"]
            if learning:
                console.print(f"\n  [yellow]{t('growth_gaps_learning', lang)}[/yellow]")
                for g in learning:
                    p = gap_progress[g]
                    console.print(f"    \U0001f4d6 {g} ({p.reads}/3)")
            if known:
                console.print(f"\n  [bold green]{t('growth_gaps_known', lang)}[/bold green]")
                for g in known:
                    console.print(f"    \u2713 {g}")

    console.print()


@app.command()
def converge(
    weekly: bool = typer.Option(False, "--weekly", help="Force weekly scope"),
    monthly: bool = typer.Option(False, "--monthly", help="Force monthly scope"),
    days: int = typer.Option(None, help="Custom number of days to cover"),
) -> None:
    """Synthesize your recent learning into higher-level understanding."""
    from neocortex.config import get_notes_dir, load_config, load_profile
    from neocortex.converger import detect_cadence, gather_recent_notes, generate_convergence_report
    from neocortex.llm import create_provider

    cfg = load_config()
    prof = load_profile()
    lang = _get_lang()

    try:
        provider = create_provider(cfg)
    except ValueError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
        raise typer.Exit(1)

    notes_dir = get_notes_dir()
    scope_days = days or (30 if monthly else 7 if weekly else 7)
    notes = gather_recent_notes(notes_dir, scope_days)

    if not notes:
        console.print(f"  [yellow]{t('converge_no_notes', lang)}[/yellow]")
        return

    cadence = "monthly" if monthly else "weekly" if weekly else detect_cadence(notes)

    console.print()
    console.print(f"  [bold]{t('converge_title', lang)}[/bold]")
    console.print(f"  [dim]{t('converge_scope', lang, count=str(len(notes)), days=str(scope_days), cadence=cadence)}[/dim]")

    async def _run() -> str:
        with console.status(f"  {t('converge_generating', lang)}"):
            return await generate_convergence_report(notes, cadence, prof, provider, lang)

    report = asyncio.run(_run())

    console.print()
    from rich.markdown import Markdown
    console.print(Markdown(report))

    today = date.today().isoformat()
    report_filename = f"convergence-{cadence}-{today}.md"
    report_path = notes_dir / report_filename
    header = f"# {t('converge_title', lang)} ({cadence})\n\n> {today} | {len(notes)} notes\n\n"
    report_path.write_text(header + report, encoding="utf-8")
    console.print()
    console.print(f"  [green]{t('converge_saved', lang, path=str(report_path))}[/green]")

    from neocortex.reader.visual import generate_html_note, has_mermaid_diagrams
    if has_mermaid_diagrams(report):
        html = generate_html_note(header + report, f"Convergence ({cadence})", "neocortex converge", lang.value)
        html_path = report_path.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")


@app.command()
def opportunities(
    opp_type: str = typer.Option("oss", "--type", help="Type: oss or job"),
    fetch: bool = typer.Option(True, help="Fetch fresh data from APIs"),
    limit: int = typer.Option(10, help="Max results"),
) -> None:
    """Find open source and job opportunities matching your skills."""
    from neocortex.config import load_config, load_profile

    cfg = load_config()
    prof = load_profile()
    lang = _get_lang()

    if not prof.skills.languages:
        console.print(f"  {t('profile_empty', lang)}")
        raise typer.Exit(1)

    if opp_type == "oss":
        from neocortex.matcher.github import find_oss_opportunities

        console.print()
        console.print(f"  [bold]{t('opp_title', lang)}[/bold]")
        console.print("  " + "\u2501" * 52)

        async def _run() -> list:
            with console.status(f"  {t('opp_searching', lang)}"):
                return await find_oss_opportunities(prof, limit)

        opps = asyncio.run(_run())

        if not opps:
            console.print(f"  [yellow]{t('opp_empty', lang)}[/yellow]")
            return

        for i, opp in enumerate(opps, 1):
            score_pct = f"{opp.match_score:.0%}"
            score_color = "green" if opp.match_score >= 0.6 else "yellow" if opp.match_score >= 0.3 else "dim"
            console.print()
            console.print(f"  [{score_color}]{score_pct}[/{score_color}] [bold cyan]{i}. {opp.title}[/bold cyan]")
            console.print(f"       [dim]{opp.url}[/dim]")
            if opp.skills_matched:
                console.print(f"       [green]\u2713 {', '.join(opp.skills_matched)}[/green]")
            if opp.skills_missing:
                console.print(f"       [yellow]\u25b3 {t('opp_missing', lang)}: {', '.join(opp.skills_missing)}[/yellow]")

        console.print()
    else:
        console.print(f"  [dim]{t('opp_jobs_coming', lang)}[/dim]")
