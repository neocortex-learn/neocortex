"""Compile command — build a linked concept wiki from notes."""

from __future__ import annotations

import asyncio

import typer

from neocortex.cli import _get_lang, app, console
from neocortex.i18n import t


@app.command()
def compile(
    full: bool = typer.Option(False, "--full", help="Full recompilation (ignore cache)"),
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
        from neocortex.compiler import compile_all

        md_files = [
            f for f in notes_dir.rglob("*.md")
            if "concepts" not in f.parts
            and "insights" not in f.parts
            and f.name != "INDEX.md"
            and "diagrams" not in f.parts
        ]

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

        console.print()

    asyncio.run(_run_compile())
