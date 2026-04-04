"""Research command — search the web to expand knowledge base."""

from __future__ import annotations

import asyncio

import typer

from neocortex.cli import _get_lang, app, console
from neocortex.i18n import t


@app.command()
def research(
    topic: str = typer.Argument(..., help="Topic or question to research"),
    count: int = typer.Option(5, help="Max articles to show"),
) -> None:
    """Search the web for articles related to a topic and your skill gaps."""
    from neocortex.config import load_config, load_profile
    from neocortex.llm import create_provider

    cfg = load_config()
    lang = cfg.output_settings.language
    prof = load_profile()

    try:
        provider = create_provider(cfg)
    except ValueError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
        raise typer.Exit(1)

    async def _run() -> None:
        from neocortex.researcher import (
            SearchResult,
            analyze_gaps_for_query,
            rank_results,
            web_search,
        )

        with console.status(f"  {t('research_analyzing', lang)}"):
            queries = await analyze_gaps_for_query(topic, prof, provider, lang)

        console.print()
        console.print(f"  [bold]{t('research_title', lang)}[/bold]")
        console.print("  " + "\u2501" * 52)
        console.print()

        console.print(f"  [dim]{t('research_queries', lang, count=str(len(queries)))}[/dim]")
        for q in queries:
            console.print(f"    [dim]- {q}[/dim]")
        console.print()

        all_results: list[SearchResult] = []
        seen_urls: set[str] = set()

        with console.status(f"  {t('research_searching', lang)}"):
            for query in queries:
                results = web_search(query, max_results=5)
                for r in results:
                    if r.url not in seen_urls:
                        seen_urls.add(r.url)
                        all_results.append(r)

        if not all_results:
            console.print(f"  {t('research_no_results', lang)}")
            console.print()
            return

        console.print(f"  [dim]{t('research_found', lang, count=str(len(all_results)))}[/dim]")

        with console.status(f"  {t('research_ranking', lang)}"):
            ranked = await rank_results(all_results, topic, prof, provider, lang, max_results=count)

        if not ranked:
            console.print(f"  {t('research_no_results', lang)}")
            console.print()
            return

        console.print()
        console.print(f"  [bold]{t('research_results', lang, count=str(len(ranked)))}[/bold]")
        console.print()

        for i, r in enumerate(ranked, 1):
            console.print(f"  [cyan]{i}.[/cyan] [bold]{r.title}[/bold]")
            console.print(f"     [dim]{r.snippet[:120]}[/dim]")
            console.print(f"     [blue]{r.url}[/blue]")
            console.print()

        console.print(f"  [dim]{t('research_read_hint', lang)}[/dim]")
        console.print()

        try:
            from InquirerPy import inquirer

            choices = [
                {"name": f"{r.title}  ({r.url[:60]})", "value": r.url}
                for r in ranked
            ]
            selected = inquirer.checkbox(
                message=t("research_select", lang),
                choices=choices,
                cycle=False,
            ).execute()
        except (ImportError, Exception):
            from rich.prompt import Prompt
            nums = Prompt.ask(
                f"  [bold]?[/bold] {t('research_select_nums', lang)}",
                default="",
                console=console,
            )
            selected = []
            for n in nums.replace(",", " ").split():
                if n.strip().isdigit():
                    idx = int(n.strip()) - 1
                    if 0 <= idx < len(ranked):
                        selected.append(ranked[idx].url)

        if not selected:
            console.print()
            return

        from neocortex.reader.fetcher import ContentFetcher
        from neocortex.reader.teacher import generate_notes, generate_outline
        from neocortex.config import get_data_dir, get_notes_dir, save_profile
        from neocortex.search import NoteIndex
        from datetime import date
        from pathlib import Path

        notes_dir = get_notes_dir()
        fetcher = ContentFetcher(provider=provider)
        generated: list[str] = []

        for url in selected:
            console.print()
            console.print(f"  [bold]>>> {url}[/bold]")

            try:
                with console.status(f"  {t('read_fetching', lang)}"):
                    doc = await fetcher.fetch(url)

                with console.status(f"  {t('analyzing', lang)}"):
                    outline = await generate_outline(doc, prof, provider)

                with console.status(f"  {t('read_generating', lang)}"):
                    notes_content = await generate_notes(doc, outline, prof, provider)

                safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in doc.title)
                safe_title = safe_title.strip().replace(" ", "-").lower()[:60] or "note"
                today = date.today().isoformat()

                from neocortex.cmd_read import _resolve_topic_dir
                topic_dir = _resolve_topic_dir(notes_dir, doc, outline, prof)
                topic_dir.mkdir(parents=True, exist_ok=True)

                filename = f"{safe_title}-{today}.md"
                note_path = topic_dir / filename
                counter = 1
                while note_path.exists():
                    counter += 1
                    filename = f"{safe_title}-{today}-{counter}.md"
                    note_path = topic_dir / filename

                frontmatter_lines = [
                    "---",
                    f"title: \"{doc.title.replace(chr(34), chr(39))}\"",
                    f"source: \"{url.replace(chr(34), chr(39))}\"",
                    f"date: {today}",
                    f"via: research",
                    f"research_topic: \"{topic.replace(chr(34), chr(39))}\"",
                ]
                deep_topics = [item.title for item in outline.items if item.marker == "deep"]
                if deep_topics:
                    frontmatter_lines.append("tags:")
                    for dt in deep_topics[:5]:
                        safe_tag = dt.strip().replace(" ", "-").lower()[:30]
                        if safe_tag:
                            frontmatter_lines.append(f"  - {safe_tag}")
                frontmatter_lines.append("---")
                frontmatter_lines.append("")

                full_content = "\n".join(frontmatter_lines) + notes_content
                note_path.write_text(full_content, encoding="utf-8")

                note_index = NoteIndex(get_data_dir() / "neocortex.sqlite")
                note_index.index_note(note_path.name, doc.title, full_content)

                try:
                    from neocortex.compiler import compile_note
                    await compile_note(note_path, notes_dir, prof, provider, lang)
                except Exception:
                    pass

                console.print(f"  [green]{t('read_saved', lang, path=str(note_path))}[/green]")
                generated.append(note_path.name)
            except Exception as exc:
                console.print(f"  [red]{t('error', lang)}: {exc}[/red]")

        if generated:
            console.print()
            console.print(f"  [bold green]{t('research_done', lang, count=str(len(generated)))}[/bold green]")
            console.print()

    asyncio.run(_run())
