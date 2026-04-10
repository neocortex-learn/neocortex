"""Search command — find anything in your knowledge base."""

from __future__ import annotations

from pathlib import Path

import typer

from neocortex.cli import _get_lang, app, console
from neocortex.i18n import t


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
) -> None:
    """Search across all notes, clips, concepts, and insights."""
    from neocortex.config import get_notes_dir
    from neocortex.search import NoteIndex

    lang = _get_lang()
    notes_dir = get_notes_dir()
    db_path = notes_dir / ".search.db"
    index = NoteIndex(db_path)

    if not index.has_index():
        console.print(f"  [yellow]{t('search_no_index', lang)}[/yellow]")
        console.print(f"  [dim]{t('search_build_hint', lang)}[/dim]")
        return

    results = index.hybrid_search(query, limit=limit)

    if not results:
        console.print(f"  [dim]{t('search_no_results', lang, query=query)}[/dim]")
        return

    console.print(f"  [bold]{t('search_found', lang, count=len(results), query=query)}[/bold]")
    console.print()

    for i, r in enumerate(results, 1):
        filename = r["filename"]
        filepath = notes_dir / filename

        # Determine content type from path
        parts = Path(filename).parts
        if "clips" in parts:
            badge = "[magenta]clip[/magenta]"
        elif "concepts" in parts:
            badge = "[cyan]concept[/cyan]"
        elif "insights" in parts:
            badge = "[green]insight[/green]"
        else:
            badge = "[blue]note[/blue]"

        # Get title
        title = Path(filename).stem
        if filepath.exists():
            try:
                for line in filepath.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if stripped.startswith("# "):
                        title = stripped[2:].strip()
                        break
            except (OSError, UnicodeDecodeError):
                pass

        # Show snippet if available
        snippet = r.get("snippet", "")
        score = r.get("score", 0)

        console.print(f"  {i}. {badge} [bold]{title}[/bold]")
        if snippet:
            # Clean up FTS5 highlight markers
            clean = snippet.replace(">>>", "[yellow]").replace("<<<", "[/yellow]")
            console.print(f"     {clean}")
        console.print(f"     [dim]{filename}[/dim]")
        console.print()
