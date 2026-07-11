"""Compile command — build a linked concept wiki from notes."""

from __future__ import annotations

from neocortex._async import run_async

import typer

from neocortex.cli import console, kb_app
from neocortex.i18n import t


@kb_app.command()
def compile(
    full: bool = typer.Option(False, "--full", help="Full recompilation (ignore cache)"),
    verify: bool = typer.Option(False, "--verify", help="Verify fidelity after compile"),
) -> None:
    """Compile notes into a linked concept wiki."""
    from neocortex.config import get_notes_dir, load_config, load_profile
    from neocortex.llm import create_provider

    cfg = load_config()
    lang = cfg.output_settings.language
    prof = load_profile()

    try:
        provider = create_provider(cfg)
    except ValueError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
        raise typer.Exit(1)

    notes_dir = get_notes_dir()

    async def _run_compile() -> None:
        from neocortex.compiler import collect_compilable_notes, compile_all

        md_files = collect_compilable_notes(notes_dir)

        if not md_files:
            console.print(f"  {t('compile_no_notes', lang)}")
            return

        console.print()
        console.print(f"  [bold]{t('compile_title', lang)}[/bold]")
        console.print()

        def on_progress(current: int, total: int) -> None:
            console.print(f"  {t('compile_progress', lang, current=str(current), total=str(total))}", end="\r")

        with console.status(f"  {t('compile_scanning', lang)}"):
            result = await compile_all(
                notes_dir, prof, provider, lang,
                on_progress=on_progress,
                force=full,
            )

        console.print()

        if result.notes_processed == 0:
            skipped = len(md_files)
            console.print(f"  [dim]{t('compile_cached', lang, skipped=str(skipped))}[/dim]")
        else:
            console.print(
                f"  [green]{t('compile_result', lang, notes=str(result.notes_processed), concepts=str(result.concepts_created + result.concepts_updated), links=str(result.wikilinks_inserted))}[/green]"
            )

        if result.concepts_created + result.concepts_updated > 0:
            console.print(
                f"  [dim]{t('compile_done', lang, created=str(result.concepts_created), updated=str(result.concepts_updated))}[/dim]"
            )

        for warning in result.warnings:
            console.print(f"  [yellow]{warning}[/yellow]")

        console.print()

        from neocortex.config import append_log
        if result.notes_processed > 0:
            append_log("compile", f"{result.notes_processed} notes, {result.concepts_created + result.concepts_updated} concepts")

        if verify and result.notes_processed > 0:
            from neocortex.verifier import verify_knowledge_base

            console.print(f"  [bold]{t('verify_title', lang)}[/bold]")
            console.print()

            v_report = await verify_knowledge_base(
                notes_dir, provider, language=lang, depth="standard",
            )

            if v_report.fidelity_score >= 80:
                score_style = "green"
            elif v_report.fidelity_score >= 50:
                score_style = "yellow"
            else:
                score_style = "red"

            console.print(
                f"  [{score_style}]{t('verify_score', lang, score=str(v_report.fidelity_score))}[/{score_style}]"
            )
            console.print(
                f"  [dim]{t('verify_summary', lang, concepts=str(v_report.concepts_verified), facts=str(v_report.total_facts), unsupported=str(v_report.unsupported))}[/dim]"
            )
            console.print()

            from neocortex.cmd_verify import _save_verify_report
            _save_verify_report(notes_dir, v_report)

    run_async(_run_compile())
