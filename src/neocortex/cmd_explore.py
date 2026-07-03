"""Explore command — scan an author/site's articles and rank by relevance."""

from __future__ import annotations

from neocortex._async import run_async
import uuid
from datetime import date, timedelta

import typer

from neocortex.cli import _get_lang, console, discover_app
from neocortex.i18n import t


@discover_app.command()
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

        # 获取已读文章标题，避免重复推荐
        notes_dir = get_notes_dir()
        already_read: list[str] = []
        for topic_read in prof.learning_history.topics_read:
            already_read.append(topic_read.title)

        with console.status(f"  {t('explore_scanning', lang)}"):
            author_overview, results = await batch_scan_articles(
                articles, prof, provider, lang,
                already_read=already_read if already_read else None,
            )

        console.print()
        console.print(f"  [bold]{t('explore_title', lang)}[/bold]")
        console.print("  " + "\u2501" * 52)

        if author_overview:
            console.print(f"  [dim]{author_overview}[/dim]")
        console.print()

        # 过滤掉被标记为跳过的结果（中英文重复等）
        skip_words = ("跳过", "skip", "duplicate", "重复", "英文版本")
        results = [
            r for r in results
            if not any(w in r.get("reason", "").lower() for w in skip_words)
        ]

        if not results:
            console.print(f"  {t('explore_no_articles', lang)}")
            return

        priority_colors = {"P0": "red bold", "P1": "yellow", "P2": "dim"}
        display_num = 1
        for priority in ("P0", "P1", "P2"):
            group = [r for r in results if r["priority"] == priority]
            if not group:
                continue
            style = priority_colors[priority]
            console.print(f"  [{style}]{priority}[/{style}]")
            for r in group:
                r["_display_num"] = display_num
                console.print(f"    {display_num}. {r['title']}")
                if r.get("reason"):
                    console.print(f"       [dim]{r['reason']}[/dim]")
                display_num += 1
            console.print()

        from rich.prompt import Prompt

        nums = Prompt.ask(
            f"  [bold]?[/bold] {t('explore_select_nums', lang)}",
            default="",
            console=console,
        )
        selected: list[str] = []
        for n in nums.replace(",", " ").split():
            if n.strip().isdigit():
                num = int(n.strip())
                for r in results:
                    if r.get("_display_num") == num:
                        selected.append(r["url"])
                        break

        selected_set = set(selected)
        notes_dir = get_notes_dir()

        # 只存 P0 和 P1 的未选中文章为 clip，P2 不存（太多了）
        unselected = [r for r in results if r["url"] not in selected_set and r["priority"] in ("P0", "P1")]
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
            from neocortex.reader.fetcher import ContentFetcher
            from neocortex.reader.teacher import generate_notes, generate_outline
            from neocortex.config import get_data_dir
            from neocortex.search import NoteIndex
            from neocortex.cmd_read import _resolve_topic_dir

            fetcher = ContentFetcher(provider=provider)

            for article_url in selected:
                console.print()
                console.print(f"  [bold]>>> {article_url}[/bold]")
                try:
                    with console.status(f"  {t('read_fetching', lang)}"):
                        doc = await fetcher.fetch(article_url)

                    with console.status(f"  {t('analyzing', lang)}"):
                        outline = await generate_outline(doc, prof, provider)

                    with console.status(f"  {t('read_generating', lang)}"):
                        notes_content = await generate_notes(doc, outline, prof, provider)

                    topic_dir = _resolve_topic_dir(notes_dir, doc, outline, prof)
                    topic_dir.mkdir(parents=True, exist_ok=True)

                    safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in doc.title)
                    safe_title = safe_title.strip().replace(" ", "-").lower()[:60] or "note"
                    today_str = date.today().isoformat()
                    filename = f"{safe_title}-{today_str}.md"
                    note_path = topic_dir / filename
                    counter = 1
                    while note_path.exists():
                        counter += 1
                        filename = f"{safe_title}-{today_str}-{counter}.md"
                        note_path = topic_dir / filename

                    frontmatter_lines = [
                        "---",
                        f"title: \"{doc.title.replace(chr(34), chr(39))}\"",
                        f"source: \"{article_url.replace(chr(34), chr(39))}\"",
                        f"date: {today_str}",
                        "via: explore",
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

                    console.print(f"  [green]{t('read_saved', lang, path=str(note_path))}[/green]")

                    note_index = NoteIndex(get_data_dir() / "neocortex.sqlite")
                    try:
                        rel = str(note_path.relative_to(notes_dir))
                    except ValueError:
                        rel = note_path.name
                    note_index.index_note(rel, doc.title, full_content)

                    try:
                        from neocortex.compiler import compile_note
                        await compile_note(note_path, notes_dir, prof, provider, lang)
                    except Exception:
                        pass

                except Exception as exc:
                    console.print(f"  [red]{t('error', lang)}: {exc}[/red]")

            console.print()

    run_async(_run())
