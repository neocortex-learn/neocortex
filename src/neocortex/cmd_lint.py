"""Lint command — knowledge base health checks."""

from __future__ import annotations

import asyncio

import typer

from neocortex.cli import app, console
from neocortex.i18n import t


@app.command()
def lint(
    fix: bool = typer.Option(False, "--fix", help="Auto-fix issues"),
) -> None:
    """Run health checks on your knowledge base."""
    from neocortex.config import get_notes_dir, load_config, load_profile

    cfg = load_config()
    lang = cfg.output_settings.language
    prof = load_profile()
    notes_dir = get_notes_dir()

    provider = None
    try:
        from neocortex.llm import create_provider
        provider = create_provider(cfg)
    except (ValueError, Exception):
        pass

    async def _run_lint() -> None:
        from neocortex.linter import fix_broken_links, lint_knowledge_base

        with console.status(f"  {t('lint_checking', lang)}"):
            report = await lint_knowledge_base(notes_dir, prof, provider, lang)

        console.print()
        console.print(f"  [bold]{t('lint_title', lang)}[/bold]")
        console.print("  " + "\u2501" * 32)
        console.print()

        if report.score >= 80:
            score_style = "green"
        elif report.score >= 50:
            score_style = "yellow"
        else:
            score_style = "red"
        console.print(f"  [{score_style}]{t('lint_score', lang, score=str(report.score))}[/{score_style}]")
        console.print()

        if not report.issues:
            console.print(f"  [green]{t('lint_no_issues', lang)}[/green]")
            console.print()
            return

        _SECTION_CONFIG = [
            ("broken_link", "lint_broken_links", "\u274c", "red"),
            ("orphan", "lint_orphan_notes", "\u26a0\ufe0f", "yellow"),
            ("stale", "lint_stale_concepts", "\u26a0\ufe0f", "yellow"),
            ("coverage_gap", "lint_coverage_gaps", "\u26a0\ufe0f", "yellow"),
            ("duplicate", "lint_duplicate_concepts", "\u26a0\ufe0f", "yellow"),
            ("decaying", "lint_decaying", "\u23f3", "yellow"),
            ("suggestion", "lint_suggested", "\U0001f4a1", "cyan"),
        ]

        passed: list[str] = []

        for issue_type, label_key, icon, color in _SECTION_CONFIG:
            type_issues = [i for i in report.issues if i.type == issue_type]
            if not type_issues:
                passed.append(t(label_key, lang))
                continue
            console.print(f"  {icon} [{color}]{t(label_key, lang)} ({len(type_issues)})[/{color}]")
            for issue in type_issues:
                console.print(f"     \u2022 {issue.message}")
                if issue.details and issue.type == "suggestion":
                    console.print(f"       [dim]{issue.details}[/dim]")
            console.print()

        if passed:
            console.print(f"  [green]\u2705 {t('lint_passed', lang)}: {', '.join(passed)}[/green]")
            console.print()

        if fix:
            total_fixed = 0

            broken_count = report.stats.get("broken_link", 0)
            if broken_count > 0:
                total_fixed += fix_broken_links(notes_dir)

            if total_fixed > 0:
                console.print(f"  [green]{t('lint_fixed', lang, count=str(total_fixed))}[/green]")
                console.print()

    asyncio.run(_run_lint())
