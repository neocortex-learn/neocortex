"""Clip command — capture fragments to the knowledge base."""

from __future__ import annotations

import asyncio
import subprocess
import uuid
from datetime import date, timedelta

import typer

from neocortex.cli import _get_lang, app, console
from neocortex.i18n import t


@app.command()
def clip(
    source: str = typer.Argument(None, help="URL, text, or file path to clip"),
    paste: bool = typer.Option(False, "--paste", help="Clip from clipboard"),
) -> None:
    """Capture a fragment to your knowledge base."""
    from neocortex.config import get_notes_dir, load_config, load_profile, save_clip
    from neocortex.models import Clip

    lang = _get_lang()

    raw_input = ""
    if paste:
        try:
            result = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            raw_input = result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass

    if not raw_input and source:
        raw_input = source

    if not raw_input:
        console.print(f"  [dim]{t('clip_empty', lang)}[/dim]")
        raise typer.Exit(0)

    cfg = load_config()
    profile = load_profile()
    notes_dir = get_notes_dir()

    async def _run() -> None:
        from neocortex.clipper import fetch_clip_content, process_clip

        with console.status(f"  {t('clip_fetching', lang)}"):
            fetched = await fetch_clip_content(raw_input)

        title = fetched["title"]
        content = fetched["content"]
        clip_type = fetched["clip_type"]
        clip_source = fetched["source"]

        # 自动检测内容长度，长文章提示升级为 read
        word_count = len(content.split())
        is_url = raw_input.startswith(("http://", "https://"))
        if is_url and word_count > 500 and clip_type == "bookmark":
            from rich.prompt import Prompt as ClipPrompt

            console.print()
            console.print(f"  [dim]{t('clip_long_detected', lang, words=str(word_count))}[/dim]")
            choice = ClipPrompt.ask(
                f"  [bold]?[/bold] {t('clip_or_read', lang)}",
                choices=["c", "r"],
                default="r",
                console=console,
            )
            if choice == "r":
                # 直接进入 read pipeline
                from neocortex.reader.fetcher import ContentFetcher
                from neocortex.reader.teacher import generate_notes, generate_outline
                from neocortex.config import get_data_dir, save_profile
                from neocortex.search import NoteIndex
                from neocortex.cmd_read import _resolve_topic_dir
                from neocortex.llm import create_provider

                try:
                    provider = create_provider(cfg)
                except ValueError as exc:
                    console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
                    return

                fetcher = ContentFetcher(provider=provider)
                with console.status(f"  {t('read_fetching', lang)}"):
                    doc = await fetcher.fetch(clip_source)

                with console.status(f"  {t('analyzing', lang)}"):
                    outline = await generate_outline(doc, profile, provider)

                with console.status(f"  {t('read_generating', lang)}"):
                    notes_content = await generate_notes(doc, outline, profile, provider)

                topic_dir = _resolve_topic_dir(notes_dir, doc, outline, profile)
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
                    f"source: \"{clip_source.replace(chr(34), chr(39))}\"",
                    f"date: {today_str}",
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
                note_index.index_note(note_path.name, doc.title, full_content)

                try:
                    from neocortex.compiler import compile_note
                    with console.status(f"  {t('compile_updating', lang)}"):
                        await compile_note(note_path, notes_dir, profile, provider, lang)
                except Exception:
                    pass

                console.print()
                return

        processed = {
            "summary": "",
            "relevance": "",
            "related_concepts": [],
            "auto_tags": [],
            "topic": "general",
        }

        if cfg.provider and cfg.api_key:
            try:
                from neocortex.llm import create_provider

                provider = create_provider(cfg)
                with console.status(f"  {t('clip_processing', lang)}"):
                    processed = await process_clip(
                        content,
                        title,
                        profile,
                        provider,
                        lang,
                        notes_dir=notes_dir,
                    )
            except (ValueError, Exception):
                pass

        today = date.today()
        clip_obj = Clip(
            id=uuid.uuid4().hex[:8],
            source=clip_source,
            content=content,
            title=title,
            clip_type=clip_type,
            auto_tags=processed.get("auto_tags", []),
            related_concepts=processed.get("related_concepts", []),
            status="inbox",
            summary=processed.get("summary", ""),
            relevance=processed.get("relevance", ""),
            priority="",
            topic=processed.get("topic", "general"),
            created_at=today.isoformat(),
            processed_at=today.isoformat() if processed.get("summary") else None,
            next_surface=(today + timedelta(days=3)).isoformat(),
        )

        saved_path = save_clip(notes_dir, clip_obj)

        try:
            from neocortex.config import get_data_dir
            from neocortex.search import NoteIndex

            idx = NoteIndex(get_data_dir() / "neocortex.sqlite")
            idx.index_note(saved_path.name, clip_obj.title or raw_input[:50], clip_obj.content)
        except Exception:
            pass

        console.print()
        console.print(f"  [green]{t('clip_saved', lang)}[/green]")
        console.print()
        console.print(f"  [bold]{clip_obj.title or raw_input[:50]}[/bold]")
        if clip_obj.summary:
            console.print(f"  [dim]{t('clip_summary', lang)}:[/dim] {clip_obj.summary}")
        if clip_obj.related_concepts:
            concepts_str = ", ".join(f"[[{c}]]" for c in clip_obj.related_concepts)
            console.print(f"  [dim]{t('clip_related', lang)}:[/dim] {concepts_str}")
        if clip_obj.relevance:
            console.print(f"  [dim]{t('clip_relevance', lang)}:[/dim] {clip_obj.relevance}")
        console.print(f"  [dim]{t('clip_topic', lang)}:[/dim] {clip_obj.topic}")
        console.print()

    asyncio.run(_run())


_CLIP_TYPE_ICONS: dict[str, str] = {
    "tweet": "\U0001f426",
    "bookmark": "\U0001f516",
    "thought": "\U0001f4ad",
    "snippet": "\U0001f4dd",
    "quote": "\U0001f4ac",
}


@app.command()
def inbox(
    process: bool = typer.Option(False, "--process", help="Interactive triage"),
    auto: bool = typer.Option(False, "--auto", help="AI batch processing"),
    synthesize: bool = typer.Option(False, "--synthesize", help="Synthesize clip clusters into notes"),
) -> None:
    """Manage your clip inbox."""
    from neocortex.config import get_notes_dir, load_clips, save_clip

    lang = _get_lang()
    notes_dir = get_notes_dir()
    all_clips = load_clips(notes_dir)
    inbox_clips = sorted(
        [c for c in all_clips if c.status == "inbox"],
        key=lambda c: c.created_at,
        reverse=True,
    )

    if process:
        _inbox_process(inbox_clips, notes_dir, lang)
        return

    if auto:
        _inbox_auto(inbox_clips, notes_dir, lang)
        return

    if synthesize:
        _inbox_synthesize(all_clips, notes_dir, lang)
        return

    _inbox_list(inbox_clips, lang)


def _inbox_list(inbox_clips: list, lang) -> None:
    from rich.table import Table

    console.print()
    console.print(f"  [bold]{t('inbox_title', lang)}[/bold]")
    console.print("  " + "\u2501" * 40)
    console.print()

    if not inbox_clips:
        console.print(f"  {t('inbox_empty', lang)}")
        console.print()
        return

    console.print(f"  [dim]{t('inbox_count', lang, count=str(len(inbox_clips)))}[/dim]")
    console.print()

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("#", style="dim")
    table.add_column("Type")
    table.add_column("Title / Summary")
    table.add_column("Date", style="dim")

    for i, clip in enumerate(inbox_clips, 1):
        icon = _CLIP_TYPE_ICONS.get(clip.clip_type, "\U0001f4dd")
        label = clip.title or clip.summary or clip.content
        if len(label) > 50:
            label = label[:50] + "..."
        table.add_row(str(i), icon, label, clip.created_at)

    console.print(table)
    console.print()


def _inbox_process(inbox_clips: list, notes_dir, lang) -> None:
    from rich.panel import Panel
    from rich.prompt import Prompt

    from neocortex.config import save_clip

    if not inbox_clips:
        console.print(f"  {t('inbox_empty', lang)}")
        return

    today = date.today().isoformat()

    for clip in inbox_clips:
        icon = _CLIP_TYPE_ICONS.get(clip.clip_type, "\U0001f4dd")
        lines = [f"[bold]{icon} {clip.title or '(untitled)'}[/bold]"]
        if clip.summary:
            lines.append(f"[dim]{clip.summary}[/dim]")
        if clip.related_concepts:
            concepts_str = ", ".join(f"[[{c}]]" for c in clip.related_concepts)
            lines.append(f"Related: {concepts_str}")
        if clip.relevance:
            lines.append(f"For you: {clip.relevance}")
        console.print(Panel("\n".join(lines), border_style="blue"))

        answer = Prompt.ask(
            "  [k]eep / [d]elete / [r]ead / [s]kip",
            choices=["k", "d", "r", "s"],
            default="s",
            console=console,
        )

        if answer == "k":
            clip.status = "reference"
            clip.processed_at = today
            save_clip(notes_dir, clip)
            console.print(f"  [green]{t('inbox_keep', lang)}[/green]")
        elif answer == "d":
            clip.status = "archived"
            clip.processed_at = today
            save_clip(notes_dir, clip)
            console.print(f"  [yellow]{t('inbox_deleted', lang)}[/yellow]")
        elif answer == "r":
            clip.status = "promoted"
            clip.promoted_to = clip.source
            clip.processed_at = today
            save_clip(notes_dir, clip)
            console.print(f"  [cyan]{t('inbox_promoted', lang, url=clip.source)}[/cyan]")
        console.print()


def _inbox_auto(inbox_clips: list, notes_dir, lang) -> None:
    import json as json_lib

    from neocortex.config import load_config, save_clip

    if not inbox_clips:
        console.print(f"  {t('inbox_empty', lang)}")
        return

    cfg = load_config()
    if not cfg.provider or not cfg.api_key:
        console.print(f"  [red]{t('config_no_provider', lang)}[/red]")
        return

    clip_list = []
    for i, clip in enumerate(inbox_clips):
        clip_list.append(f"{i}. [{clip.clip_type}] {clip.title or '(untitled)'}: {clip.summary or clip.content[:100]}")

    prompt_text = (
        "Prioritize the following clips for a developer's inbox.\n"
        "Assign each a priority: P0 (must-read/act), P1 (useful), P2 (low priority).\n\n"
        + "\n".join(clip_list)
        + "\n\nOutput JSON array: [{\"index\": 0, \"priority\": \"P0\"}, ...]"
    )

    async def _run() -> None:
        from neocortex.llm import create_provider

        try:
            provider = create_provider(cfg)
        except ValueError as exc:
            console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
            return

        with console.status(f"  {t('clip_processing', lang)}"):
            try:
                raw = await provider.chat(
                    [{"role": "user", "content": prompt_text}],
                    json_mode=True,
                )
                results = json_lib.loads(raw)
            except Exception:
                results = []

        if not isinstance(results, list):
            results = []

        priority_map = {}
        for item in results:
            if isinstance(item, dict) and "index" in item and "priority" in item:
                priority_map[item["index"]] = item["priority"]

        updated = 0
        for i, clip in enumerate(inbox_clips):
            pri = priority_map.get(i, "")
            if pri:
                clip.priority = pri
                save_clip(notes_dir, clip)
                updated += 1

        console.print(f"  [green]{t('inbox_auto_done', lang, count=str(updated))}[/green]")

    asyncio.run(_run())


def _inbox_synthesize(all_clips: list, notes_dir, lang) -> None:
    import json as json_lib
    import os
    import tempfile

    from neocortex.config import load_config, save_clip

    active_clips = [c for c in all_clips if c.status in ("inbox", "reference")]
    concept_groups: dict[str, list] = {}
    for clip in active_clips:
        for concept in clip.related_concepts:
            concept_groups.setdefault(concept, []).append(clip)

    clusters = {k: v for k, v in concept_groups.items() if len(v) >= 3}

    if not clusters:
        console.print(f"  {t('inbox_no_clusters', lang)}")
        return

    cfg = load_config()
    if not cfg.provider or not cfg.api_key:
        console.print(f"  [red]{t('config_no_provider', lang)}[/red]")
        return

    async def _run() -> None:
        from neocortex.llm import create_provider

        try:
            provider = create_provider(cfg)
        except ValueError as exc:
            console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
            return

        synthesized_count = 0
        for concept, clips_in_cluster in clusters.items():
            clip_entries = []
            for clip in clips_in_cluster:
                clip_entries.append(
                    f"- Title: {clip.title or '(untitled)'}\n"
                    f"  Summary: {clip.summary or clip.content[:200]}\n"
                    f"  Source: {clip.source}"
                )

            prompt_text = (
                f"The user collected {len(clips_in_cluster)} clips related to [[{concept}]]:\n\n"
                + "\n".join(clip_entries)
                + "\n\n"
                "Synthesize these clips into a concise knowledge note:\n\n"
                "## Threads\nWhat direction do these clips point toward?\n\n"
                "## Consensus\nWhat common viewpoints emerge across sources?\n\n"
                "## Divergence\nAny contradictions or different angles?\n\n"
                "## Next steps\nWhat should the user explore further?\n\n"
                "Write in the user's language. Be concise and sharp."
            )

            with console.status(f"  Synthesizing [[{concept}]]..."):
                try:
                    note_content = await provider.chat(
                        [{"role": "user", "content": prompt_text}],
                    )
                except Exception:
                    continue

            slug = concept.strip().lower().replace(" ", "-")
            note_path = notes_dir / f"synthesis-{slug}.md"
            today = date.today().isoformat()
            frontmatter = (
                "---\n"
                f"source: clip-synthesis\n"
                f"date: {today}\n"
                f"tags: [synthesis, {concept}]\n"
                f"related_gaps: [{concept}]\n"
                "---\n\n"
                f"# Synthesis: {concept}\n\n"
            )
            full_content = frontmatter + note_content

            fd, tmp_path = tempfile.mkstemp(dir=str(notes_dir), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(full_content)
                os.replace(tmp_path, str(note_path))
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                continue

            for clip in clips_in_cluster:
                clip.status = "synthesized"
                clip.processed_at = today
                save_clip(notes_dir, clip)

            synthesized_count += 1

        console.print(f"  [green]{t('inbox_synthesize_done', lang, count=str(synthesized_count))}[/green]")

    asyncio.run(_run())
