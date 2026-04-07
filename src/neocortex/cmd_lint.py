"""Lint command — knowledge base health checks."""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
from datetime import date
from pathlib import Path

import typer

from neocortex.cli import console, kb_app
from neocortex.i18n import t
from neocortex.models import LintReport


def _save_lint_report(notes_dir: Path, report: LintReport) -> Path:
    """Save a lint report to _reports/lint-{date}.md and prune old reports."""
    reports_dir = notes_dir / "_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    report_path = reports_dir / f"lint-{today}.md"

    issue_lines: list[str] = []
    for issue in report.issues:
        severity_icon = {"error": "x", "warning": "!", "info": "i"}.get(issue.severity, "?")
        issue_lines.append(f"- [{severity_icon}] [{issue.type}] {issue.message}")

    content = (
        f"---\ntype: lint-report\ndate: {today}\nscore: {report.score}\n"
        f"issues: {{error: {report.stats.get('broken_link', 0)}, "
        f"warning: {sum(report.stats.get(k, 0) for k in ('orphan', 'stale', 'duplicate', 'decaying', 'coverage_gap'))}, "
        f"info: {report.stats.get('suggestion', 0)}}}\n---\n\n"
        f"# Lint Report — {today}\n\n"
        f"**Score: {report.score} / 100**\n\n"
    )
    if issue_lines:
        content += "## Issues\n\n" + "\n".join(issue_lines) + "\n"
    else:
        content += "No issues found.\n"

    fd, tmp_path = tempfile.mkstemp(dir=str(reports_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(report_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # Prune: keep only the latest 12 reports
    existing = sorted(reports_dir.glob("lint-*.md"), reverse=True)
    for old in existing[12:]:
        try:
            old.unlink()
        except OSError:
            pass

    return report_path


def _get_previous_score(notes_dir: Path) -> int | None:
    """Read the score from the most recent lint report before today."""
    reports_dir = notes_dir / "_reports"
    if not reports_dir.exists():
        return None

    today = date.today().isoformat()
    reports = sorted(reports_dir.glob("lint-*.md"), reverse=True)

    for rp in reports:
        if rp.stem == f"lint-{today}":
            continue
        try:
            content = rp.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        m = re.search(r"^score:\s*(\d+)", content, re.MULTILINE)
        if m:
            return int(m.group(1))
    return None


@kb_app.command()
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

        # Trend comparison
        prev_score = _get_previous_score(notes_dir)
        trend_str = ""
        if prev_score is not None:
            delta = report.score - prev_score
            if delta > 0:
                trend_str = f"  [green]\u25b2 +{delta} vs {t('lint_trend_last', lang)}[/green]"
            elif delta < 0:
                trend_str = f"  [red]\u25bc {delta} vs {t('lint_trend_last', lang)}[/red]"
            else:
                trend_str = f"  [dim]= vs {t('lint_trend_last', lang)}[/dim]"

        console.print(f"  [{score_style}]{t('lint_score', lang, score=str(report.score))}[/{score_style}]{trend_str}")
        console.print()

        if not report.issues:
            console.print(f"  [green]{t('lint_no_issues', lang)}[/green]")
            console.print()
            _save_lint_report(notes_dir, report)
            from neocortex.config import append_log
            delta_str = f" ({delta:+d})" if prev_score is not None and (delta := report.score - prev_score) != 0 else ""
            append_log("lint", f"score: {report.score}{delta_str}")
            return

        _SECTION_CONFIG = [
            ("broken_link", "lint_broken_links", "\u274c", "red"),
            ("orphan", "lint_orphan_notes", "\u26a0\ufe0f", "yellow"),
            ("stale", "lint_stale_concepts", "\u26a0\ufe0f", "yellow"),
            ("coverage_gap", "lint_coverage_gaps", "\u26a0\ufe0f", "yellow"),
            ("duplicate", "lint_duplicate_concepts", "\u26a0\ufe0f", "yellow"),
            ("decaying", "lint_decaying", "\u23f3", "yellow"),
            ("low_fidelity", "lint_low_fidelity", "\U0001f50d", "yellow"),
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

        _save_lint_report(notes_dir, report)

        from neocortex.config import append_log
        delta_str = f" ({delta:+d})" if prev_score is not None and (delta := report.score - prev_score) != 0 else ""
        append_log("lint", f"score: {report.score}{delta_str}")

    asyncio.run(_run_lint())
