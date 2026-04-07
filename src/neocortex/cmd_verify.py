"""Verify command — LLM output fidelity checks."""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from neocortex.cli import console, kb_app
from neocortex.i18n import t
from neocortex.models import FactVerdict, VerifyReport


def _save_verify_report(notes_dir: Path, report: VerifyReport) -> Path:
    """Save verification report to _reports/verify-{date}.md and prune old reports."""
    reports_dir = notes_dir / "_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    report_path = reports_dir / f"verify-{today}.md"

    lines: list[str] = []
    for cv in report.concept_results:
        pct = round(cv.supported_ratio * 100)
        lines.append(f"### {cv.concept_name} — {pct}% ({cv.supported_count}/{cv.total_facts})")
        for fc in cv.fact_checks:
            if fc.verdict != FactVerdict.SUPPORTED:
                tag = fc.verdict.value.upper()
                lines.append(f"- [{tag}] {fc.fact.text}")
                if fc.explanation:
                    lines.append(f"  {fc.explanation}")

    if report.overview_checks:
        lines.append("")
        lines.append("### Overview")
        for fc in report.overview_checks:
            tag = fc.verdict.value.upper()
            lines.append(f"- [{tag}] {fc.fact.text}")
            if fc.explanation:
                lines.append(f"  {fc.explanation}")

    if report.claims_checks:
        drifted = [c for c in report.claims_checks if c.verdict != FactVerdict.SUPPORTED]
        if drifted:
            lines.append("")
            lines.append("### Claims Drift")
            for fc in drifted:
                tag = fc.verdict.value.upper()
                lines.append(f"- [{tag}] {fc.fact.text}")
                if fc.explanation:
                    lines.append(f"  {fc.explanation}")

    if report.consistency_checks:
        inconsistent = [c for c in report.consistency_checks if c.verdict != FactVerdict.SUPPORTED]
        if inconsistent:
            lines.append("")
            lines.append("### Self-Consistency")
            for fc in inconsistent:
                tag = fc.verdict.value.upper()
                lines.append(f"- [{tag}] {fc.fact.text}")
                if fc.explanation:
                    lines.append(f"  {fc.explanation}")

    content = (
        f"---\ntype: verify-report\ndate: {today}\n"
        f"fidelity_score: {report.fidelity_score}\n"
        f"depth: {report.depth}\n"
        f"concepts_verified: {report.concepts_verified}\n"
        f"total_facts: {report.total_facts}\n"
        f"supported: {report.supported}\n"
        f"unsupported: {report.unsupported}\n"
        f"unverifiable: {report.unverifiable}\n---\n\n"
        f"# Verify Report — {today}\n\n"
        f"**Fidelity Score: {report.fidelity_score} / 100** | "
        f"Depth: {report.depth}\n\n"
    )
    if lines:
        content += "\n".join(lines) + "\n"
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
    existing = sorted(reports_dir.glob("verify-*.md"), reverse=True)
    for old in existing[12:]:
        try:
            old.unlink()
        except OSError:
            pass

    return report_path


def _get_previous_fidelity(notes_dir: Path) -> int | None:
    """Read fidelity score from the most recent verify report before today."""
    reports_dir = notes_dir / "_reports"
    if not reports_dir.exists():
        return None

    today = date.today().isoformat()
    reports = sorted(reports_dir.glob("verify-*.md"), reverse=True)

    for rp in reports:
        if rp.stem == f"verify-{today}":
            continue
        try:
            content = rp.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        m = re.search(r"^fidelity_score:\s*(\d+)", content, re.MULTILINE)
        if m:
            return int(m.group(1))
    return None


def _get_all_fidelity_scores(notes_dir: Path) -> list[tuple[str, int]]:
    """Read (date, score) from all verify reports, newest first."""
    reports_dir = notes_dir / "_reports"
    if not reports_dir.exists():
        return []

    results: list[tuple[str, int]] = []
    for rp in sorted(reports_dir.glob("verify-*.md"), reverse=True):
        try:
            content = rp.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        date_match = re.search(r"^date:\s*(\S+)", content, re.MULTILINE)
        score_match = re.search(r"^fidelity_score:\s*(\d+)", content, re.MULTILINE)
        if date_match and score_match:
            results.append((date_match.group(1), int(score_match.group(1))))
    return results


def _render_trend(scores: list[tuple[str, int]], width: int = 40) -> str:
    """Render a simple ASCII sparkline of fidelity scores over time."""
    if not scores:
        return ""
    # Reverse to chronological order
    scores = list(reversed(scores))
    values = [s for _, s in scores]
    lo, hi = min(values), max(values)
    span = max(hi - lo, 1)
    bars = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"

    line = ""
    for _, v in scores:
        idx = min(len(bars) - 1, int((v - lo) / span * (len(bars) - 1)))
        line += bars[idx]

    dates_line = f"  {scores[0][0]}  {'.' * max(0, len(scores) - 2)}  {scores[-1][0]}"
    return f"  {line}  ({lo}-{hi})\n{dates_line}"


def _render_bar(ratio: float, width: int = 12) -> str:
    """Render a progress bar like ██████████░░."""
    filled = round(ratio * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


@kb_app.command()
def verify(
    concept: Optional[list[str]] = typer.Option(None, "--concept", help="Verify specific concept(s)"),
    full: bool = typer.Option(False, "--full", help="Verify all concepts (ignore cache)"),
    depth: str = typer.Option("standard", "--depth", help="shallow|standard|deep"),
    fix: bool = typer.Option(False, "--fix", help="Lower confidence for low-fidelity concepts"),
    trend: bool = typer.Option(False, "--trend", help="Show fidelity score trend"),
    json_output: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Verify that compiled concepts are faithful to source notes."""
    from neocortex.config import get_notes_dir, load_config

    if trend:
        notes_dir = get_notes_dir()
        lang = load_config().output_settings.language
        scores = _get_all_fidelity_scores(notes_dir)
        console.print()
        console.print(f"  [bold]{t('verify_trend_title', lang)}[/bold]")
        console.print()
        if not scores:
            console.print(f"  [dim]{t('verify_no_reports', lang)}[/dim]")
        else:
            console.print(_render_trend(scores))
            console.print()
            for d, s in scores[:10]:
                style = "green" if s >= 80 else ("yellow" if s >= 50 else "red")
                console.print(f"  {d}  [{style}]{s:>3}/100[/{style}]")
        console.print()
        return

    from neocortex.llm import create_provider

    cfg = load_config()
    lang = cfg.output_settings.language

    provider = None
    if depth != "shallow":
        try:
            provider = create_provider(cfg)
        except ValueError as exc:
            console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
            raise typer.Exit(1)

    notes_dir = get_notes_dir()

    async def _run_verify() -> None:
        from neocortex.verifier import verify_knowledge_base

        concept_names = concept if concept else None

        with console.status(f"  {t('verify_checking', lang)}"):
            report = await verify_knowledge_base(
                notes_dir, provider, language=lang,
                concept_names=concept_names, depth=depth,
                force=full, fix=fix,
            )

        if json_output:
            console.print(report.model_dump_json(indent=2))
            return

        console.print()
        console.print(f"  [bold]{t('verify_title', lang)}[/bold]")
        console.print("  " + "\u2501" * 32)
        console.print()

        if report.concepts_verified == 0:
            if not full and not concept_names:
                console.print(f"  [dim]{t('verify_cached', lang)}[/dim]")
            else:
                console.print(f"  {t('verify_no_concepts', lang)}")
            console.print()
            return

        # Per-concept results
        for cv in report.concept_results:
            ratio = cv.supported_ratio
            bar = _render_bar(ratio)
            pct = round(ratio * 100)

            if ratio >= 0.8:
                style = "green"
            elif ratio >= 0.5:
                style = "yellow"
            else:
                style = "red"

            console.print(
                f"  {cv.concept_name:<24} [{style}]{bar}[/{style}] "
                f"[{style}]{pct:>3}%[/{style}] ({cv.supported_count}/{cv.total_facts})"
            )

            # Show unsupported/unverifiable facts
            for fc in cv.fact_checks:
                if fc.verdict == FactVerdict.UNSUPPORTED:
                    console.print(f"    [red][!] \"{fc.fact.text}\" \u2014 {t('verify_unsupported', lang)}[/red]")
                    if fc.explanation:
                        console.print(f"        [dim]{fc.explanation}[/dim]")
                elif fc.verdict == FactVerdict.UNVERIFIABLE:
                    console.print(f"    [yellow][?] \"{fc.fact.text}\" \u2014 {t('verify_unverifiable', lang)}[/yellow]")
                    if fc.explanation:
                        console.print(f"        [dim]{fc.explanation}[/dim]")

        # Overview results (deep mode)
        if report.overview_checks:
            console.print()
            overview_supported = sum(1 for c in report.overview_checks if c.verdict == FactVerdict.SUPPORTED)
            overview_total = len(report.overview_checks)
            ratio = overview_supported / overview_total if overview_total else 1.0
            bar = _render_bar(ratio)
            pct = round(ratio * 100)
            style = "green" if ratio >= 0.8 else ("yellow" if ratio >= 0.5 else "red")

            console.print(
                f"  {t('verify_overview', lang):<24} [{style}]{bar}[/{style}] "
                f"[{style}]{pct:>3}%[/{style}]"
            )
            for fc in report.overview_checks:
                if fc.verdict != FactVerdict.SUPPORTED:
                    tag = "[!]" if fc.verdict == FactVerdict.UNSUPPORTED else "[?]"
                    color = "red" if fc.verdict == FactVerdict.UNSUPPORTED else "yellow"
                    console.print(f"    [{color}]{tag} \"{fc.fact.text}\"[/{color}]")

        # Claims cross-verification results (deep mode)
        if report.claims_checks:
            drifted = [c for c in report.claims_checks if c.verdict == FactVerdict.UNSUPPORTED]
            if drifted:
                console.print()
                console.print(f"  [bold]{t('verify_claims_drift', lang)} ({len(drifted)})[/bold]")
                for fc in drifted:
                    console.print(f"    [red][!] \"{fc.fact.text}\"[/red]")
                    if fc.explanation:
                        console.print(f"        [dim]{fc.explanation}[/dim]")

        # Self-consistency results (deep mode)
        if report.consistency_checks:
            inconsistent = [c for c in report.consistency_checks if c.verdict == FactVerdict.UNVERIFIABLE]
            if inconsistent:
                console.print()
                console.print(f"  [bold]{t('verify_inconsistent', lang)} ({len(inconsistent)})[/bold]")
                for fc in inconsistent:
                    console.print(f"    [yellow][~] \"{fc.fact.text}\"[/yellow]")
                    if fc.explanation:
                        console.print(f"        [dim]{fc.explanation}[/dim]")

        console.print()
        console.print("  " + "\u2501" * 32)

        # Score and trend
        if report.fidelity_score >= 80:
            score_style = "green"
        elif report.fidelity_score >= 50:
            score_style = "yellow"
        else:
            score_style = "red"

        prev = _get_previous_fidelity(notes_dir)
        trend_str = ""
        if prev is not None:
            delta = report.fidelity_score - prev
            if delta > 0:
                trend_str = f"  [green]\u25b2 +{delta} vs {t('verify_trend_last', lang)}[/green]"
            elif delta < 0:
                trend_str = f"  [red]\u25bc {delta} vs {t('verify_trend_last', lang)}[/red]"
            else:
                trend_str = f"  [dim]= vs {t('verify_trend_last', lang)}[/dim]"

        console.print(f"  [{score_style}]{t('verify_score', lang, score=str(report.fidelity_score))}[/{score_style}]{trend_str}")

        if report.unsupported == 0 and report.total_facts > 0:
            console.print(f"  [green]{t('verify_all_supported', lang)}[/green]")
        else:
            console.print(
                f"  [dim]{t('verify_summary', lang, concepts=str(report.concepts_verified), facts=str(report.total_facts), unsupported=str(report.unsupported))}[/dim]"
            )

        if fix:
            penalized = sum(
                1 for cv in report.concept_results
                if cv.total_facts > 0 and cv.supported_ratio < 0.8
            )
            if penalized > 0:
                console.print(f"  [yellow]{t('verify_fixed', lang, count=str(penalized))}[/yellow]")

        console.print()

        # Save report
        report_path = _save_verify_report(notes_dir, report)
        rel_path = report_path.relative_to(notes_dir)
        console.print(f"  [dim]{t('verify_report_saved', lang, path=str(rel_path))}[/dim]")
        console.print()

        # Log
        from neocortex.config import append_log
        delta_str = f" ({delta:+d})" if prev is not None and (delta := report.fidelity_score - prev) != 0 else ""
        append_log("verify", f"fidelity: {report.fidelity_score}{delta_str}, {report.concepts_verified} concepts")

    asyncio.run(_run_verify())
