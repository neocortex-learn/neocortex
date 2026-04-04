"""Feed command — manage RSS feeds and discover relevant articles."""

from __future__ import annotations

import asyncio

import typer
from rich.table import Table

from neocortex.cli import _get_lang, console, discover_app
from neocortex.i18n import t


@discover_app.command()
def feed(
    add: str = typer.Option(None, help="Add a new RSS feed URL"),
    remove: str = typer.Option(None, help="Remove a feed by URL"),
    list_feeds: bool = typer.Option(False, "--list", help="List configured feeds"),
) -> None:
    """Manage RSS feeds and discover relevant articles."""
    from neocortex.config import (
        load_config,
        load_feed_history,
        load_feeds,
        load_profile,
        save_feed_history,
        save_feeds,
    )

    lang = _get_lang()
    feeds = load_feeds()

    if add is not None:
        _handle_add(add, feeds, lang, save_feeds)
        return

    if remove is not None:
        _handle_remove(remove, feeds, lang, save_feeds)
        return

    if list_feeds:
        _handle_list(feeds, lang)
        return

    _handle_fetch(feeds, lang)


def _handle_add(
    url: str,
    feeds: list[dict],
    lang: str,
    save_feeds,
) -> None:
    """Validate and add a new RSS feed."""
    import httpx

    for f in feeds:
        if f["url"] == url:
            console.print(f"  [yellow]{t('feed_added', lang, name=f.get('name', url), url=url)}[/yellow]")
            return

    with console.status(f"  {t('feed_fetching', lang)}"):
        try:
            import feedparser

            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
            parsed = feedparser.parse(resp.text)
            if not parsed.entries and not parsed.feed.get("title"):
                console.print(f"  [red]{t('feed_invalid', lang, url=url)}[/red]")
                raise typer.Exit(1)
            name = parsed.feed.get("title", url)
        except (httpx.HTTPError, OSError):
            console.print(f"  [red]{t('feed_invalid', lang, url=url)}[/red]")
            raise typer.Exit(1)

    feeds.append({"url": url, "name": name})
    save_feeds(feeds)
    console.print(f"  [green]{t('feed_added', lang, name=name, url=url)}[/green]")


def _handle_remove(
    url: str,
    feeds: list[dict],
    lang: str,
    save_feeds,
) -> None:
    """Remove a feed by URL."""
    original_len = len(feeds)
    feeds_filtered = [f for f in feeds if f["url"] != url]

    if len(feeds_filtered) == original_len:
        console.print(f"  [yellow]{t('feed_not_found', lang, url=url)}[/yellow]")
        return

    save_feeds(feeds_filtered)
    console.print(f"  [green]{t('feed_removed', lang, url=url)}[/green]")


def _handle_list(feeds: list[dict], lang: str) -> None:
    """Display configured feeds as a table."""
    if not feeds:
        console.print(f"  [dim]{t('feed_empty', lang)}[/dim]")
        return

    console.print()
    table = Table(title=t("feed_title", lang), show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("URL", style="dim")

    for f in feeds:
        table.add_row(f.get("name", ""), f["url"])

    console.print(table)
    console.print()


def _handle_fetch(feeds: list[dict], lang: str) -> None:
    """Fetch feeds, filter by gaps, display results."""
    if not feeds:
        console.print(f"  [dim]{t('feed_empty', lang)}[/dim]")
        return

    from neocortex.config import (
        load_config,
        load_feed_history,
        load_profile,
        save_feed_history,
    )

    cfg = load_config()
    profile = load_profile()
    history = load_feed_history()

    provider = None
    if cfg.provider and cfg.api_key:
        try:
            from neocortex.llm import create_provider
            provider = create_provider(cfg)
        except (ValueError, Exception):
            pass

    async def _run() -> None:
        from neocortex.feeder import fetch_feeds, filter_by_gaps

        with console.status(f"  {t('feed_fetching', lang)}"):
            items, updated_history = await fetch_feeds(feeds, history)

        save_feed_history(updated_history)

        if not items:
            console.print(f"  [dim]{t('feed_no_new', lang)}[/dim]")
            return

        with console.status(f"  {t('feed_filtering', lang)}"):
            filtered = await filter_by_gaps(items, profile, provider, lang)

        if not filtered:
            console.print(f"  [dim]{t('feed_no_new', lang)}[/dim]")
            return

        console.print()
        console.print(f"  [bold]{t('feed_results', lang, count=str(len(filtered)))}[/bold]")
        console.print()

        for i, item in enumerate(filtered, 1):
            console.print(f"  [cyan]{i}.[/cyan] [bold]{item.title}[/bold]")
            if item.feed_name:
                console.print(f"     [dim]{item.feed_name}[/dim]", end="")
                if item.published:
                    console.print(f"  [dim]({item.published})[/dim]")
                else:
                    console.print()
            if item.summary:
                clean = item.summary.replace("\n", " ").strip()
                if len(clean) > 120:
                    clean = clean[:120] + "..."
                console.print(f"     [dim]{clean}[/dim]")
            console.print(f"     {item.url}")
            console.print()

        console.print(f"  [dim]{t('feed_read_hint', lang)}[/dim]")
        console.print()

    asyncio.run(_run())
