"""Explore command — scan an author/site's articles and rank by relevance."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta

import typer

from neocortex.cli import _get_lang, app, console
from neocortex.i18n import t


@app.command()
def explore(
    url: str = typer.Argument(..., help="Archive/blog page URL"),
    no_read: bool = typer.Option(False, "--no-read", help="Skip showing read commands"),
) -> None:
    """Explore an author's articles and find what's worth reading."""
    from neocortex.config import get_notes_dir, load_config, load_profile, save_clip
    from neocortex.models import Clip

    lang = _get_lang()
    cfg = load_config()
    prof = load_profile()

    if not cfg.provider or not cfg.api_key:
        console.print(f"  [red]{t('config_no_provider', lang)}[/red]")
        raise typer.Exit(1)

    async def _run() -> None:
        from neocortex.explorer import batch_scan_articles, extract_article_links
        from neocortex.llm import create_provider

        try:
            provider = create_provider(cfg)
        except ValueError as exc:
            console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
            return

        with console.status(f"  {t('explore_fetching', lang)}"):
            try:
                articles = await extract_article_links(url)
            except Exception as exc:
                console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
                return

        if not articles:
            console.print(f"  {t('explore_no_articles', lang)}")
            return

        console.print(f"  [dim]{t('explore_found', lang, count=str(len(articles)))}[/dim]")

        with console.status(f"  {t('explore_scanning', lang)}"):
            author_overview, results = await batch_scan_articles(
                articles, prof, provider, lang,
            )

        console.print()
        console.print(f"  [bold]{t('explore_title', lang)}[/bold]")
        console.print("  " + "\u2501" * 52)

        if author_overview:
            console.print(f"  [dim]{author_overview}[/dim]")
        console.print()

        priority_colors = {"P0": "red bold", "P1": "yellow", "P2": "dim"}
        for priority in ("P0", "P1", "P2"):
            group = [r for r in results if r["priority"] == priority]
            if not group:
                continue
            style = priority_colors[priority]
            console.print(f"  [{style}]{priority}[/{style}]")
            for r in group:
                console.print(f"    {r['index'] + 1}. {r['title']}")
                if r.get("reason"):
                    console.print(f"       [dim]{r['reason']}[/dim]")
            console.print()

        try:
            from InquirerPy import inquirer

            choices = [
                {
                    "name": f"[{r['priority']}] {r['title']}",
                    "value": r["url"],
                    "enabled": r["priority"] == "P0",
                }
                for r in results
            ]
            selected = inquirer.checkbox(
                message=t("explore_select", lang),
                choices=choices,
                cycle=False,
            ).execute()
        except (ImportError, Exception):
            from rich.prompt import Prompt

            nums = Prompt.ask(
                f"  [bold]?[/bold] {t('explore_select_nums', lang)}",
                default="",
                console=console,
            )
            selected: list[str] = []
            for n in nums.replace(",", " ").split():
                if n.strip().isdigit():
                    idx = int(n.strip()) - 1
                    if 0 <= idx < len(results):
                        selected.append(results[idx]["url"])

        selected_set = set(selected)
        notes_dir = get_notes_dir()

        unselected = [r for r in results if r["url"] not in selected_set]
        if unselected:
            today = date.today()
            for r in unselected:
                clip_obj = Clip(
                    id=uuid.uuid4().hex[:8],
                    source=r["url"],
                    content=r.get("reason", ""),
                    title=r["title"],
                    clip_type="bookmark",
                    auto_tags=[],
                    related_concepts=[],
                    status="inbox",
                    summary=r.get("reason", ""),
                    priority=r.get("priority", "P2"),
                    topic="",
                    created_at=today.isoformat(),
                    next_surface=(today + timedelta(days=7)).isoformat(),
                )
                save_clip(notes_dir, clip_obj)
            console.print(
                f"  [dim]{t('explore_saved_clips', lang, count=str(len(unselected)))}[/dim]"
            )

        if selected and not no_read:
            console.print()
            console.print(f"  [bold]{t('explore_read_hint', lang)}[/bold]")
            for article_url in selected:
                console.print(f"  [cyan]neocortex read {article_url}[/cyan]")
            console.print()

    asyncio.run(_run())
