"""Import command for chat history."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from neocortex.cli import app, console
from neocortex.i18n import t


@app.command("import")
def import_data(
    path: str = typer.Argument(None, help="Path to export file/directory"),
    source: str = typer.Option(None, help="Source: chatgpt or claude"),
    clear: bool = typer.Option(False, help="Clear imported insights"),
) -> None:
    """Import chat history (chatgpt/claude) to enrich your profile."""
    from neocortex.config import load_config, load_profile, save_profile
    from neocortex.llm import create_provider

    cfg = load_config()
    lang = cfg.output_settings.language
    prof = load_profile()

    if clear:
        prof.chat_insights = None
        save_profile(prof)
        console.print(f"  {t('import_cleared', lang)}")
        return

    if not source:
        console.print("[red]--source is required (chatgpt or claude)[/red]")
        raise typer.Exit(1)
    if not path:
        console.print("[red]Path to export file is required[/red]")
        raise typer.Exit(1)

    resolved_path = Path(path).resolve()
    if not resolved_path.exists():
        console.print(f"  [red]{t('error', lang)}: Path not found: {resolved_path}[/red]")
        raise typer.Exit(1)

    valid_sources = ("chatgpt", "claude")
    if source not in valid_sources:
        console.print(f"  [red]{t('error', lang)}: Invalid source '{source}'. Valid: {', '.join(valid_sources)}[/red]")
        raise typer.Exit(1)

    try:
        provider = create_provider(cfg)
    except ValueError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
        raise typer.Exit(1)

    async def _run_import() -> None:
        from neocortex.importer.extractor import extract_insights
        from neocortex.importer.merger import cross_validate, merge_insights_to_profile

        with console.status(f"  {t('import_parsing', lang, source=source)}"):
            if source == "chatgpt":
                from neocortex.importer.chatgpt import parse_chatgpt_export
                messages = parse_chatgpt_export(str(resolved_path))
            else:
                from neocortex.importer.claude import parse_claude_export
                messages = parse_claude_export(str(resolved_path))

        if not messages:
            console.print(f"  [yellow]{t('import_no_messages', lang)}[/yellow]")
            return

        with console.status(f"  {t('import_extracting', lang, count=str(len(messages)))}"):
            insights = await extract_insights(messages, provider, source)

        merge_insights_to_profile(prof, insights)
        cross_validate(prof.skills, insights)
        save_profile(prof)

        console.print(f"  [green]{t('import_done', lang)}[/green]")

    asyncio.run(_run_import())
