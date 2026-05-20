"""Clip command — capture fragments to the knowledge base."""

from __future__ import annotations

import asyncio
import subprocess
import uuid
from datetime import date, timedelta

import typer

from neocortex.cli import _get_lang, app, console
from neocortex.i18n import t


def _try_paste_image() -> str:
    """Try to save clipboard image to a temp file. Returns path or empty string."""
    import tempfile
    try:
        # macOS: check if clipboard has image data
        check = subprocess.run(
            ["osascript", "-e", "the clipboard as «class PNGf»"],
            capture_output=True,
            timeout=5,
        )
        if check.returncode != 0:
            return ""

        # Save clipboard image to temp file
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        subprocess.run(
            ["osascript", "-e",
             f'set f to open for access POSIX file "{tmp.name}" with write permission\n'
             f'write (the clipboard as «class PNGf») to f\n'
             f'close access f'],
            capture_output=True,
            timeout=10,
        )
        import os
        if os.path.getsize(tmp.name) > 0:
            return tmp.name
        os.unlink(tmp.name)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


@app.command()
def clip(
    sources: list[str] = typer.Argument(None, help="URL, text, or file paths to clip (multiple images merged)"),
    paste: bool = typer.Option(False, "--paste", help="Clip from clipboard"),
    process: bool | None = typer.Option(
        None,
        "--process/--no-process",
        "-p",
        help="LLM 即时关联（默认：配置了 LLM key 时自动开启；--no-process 强制关闭）",
    ),
) -> None:
    """Capture a fragment to your knowledge base.

    Default behavior (Q11): if an LLM key is configured, runs immediate
    LLM tagging/relating; otherwise saves without LLM. Use --no-process
    to force-skip, or set ``clip_default_process=false`` in config.json.
    Pass multiple image files to merge them into one clip.
    """
    from neocortex.config import get_notes_dir, load_config, load_profile, save_clip
    from neocortex.models import Clip

    lang = _get_lang()
    source = sources[0] if sources and len(sources) == 1 else None

    raw_input = ""
    paste_image_path = ""
    multi_images: list[str] = []

    # Check for multiple image files
    if sources and len(sources) > 1:
        from pathlib import Path as _P
        image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}
        imgs = [s for s in sources if _P(s).expanduser().exists() and _P(s).suffix.lower() in image_exts]
        if imgs:
            multi_images = [str(_P(s).expanduser()) for s in imgs]

    if not multi_images:
        if paste:
            paste_image_path = _try_paste_image()
            if not paste_image_path:
                try:
                    result = subprocess.run(
                        ["pbpaste"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    from neocortex.clipper import _sanitize_text
                    raw_input = _sanitize_text(result.stdout.strip())
                except (OSError, subprocess.TimeoutExpired):
                    pass

        if paste_image_path:
            raw_input = paste_image_path
        elif not raw_input and source:
            raw_input = source

    if not raw_input and not multi_images:
        console.print(f"  [dim]{t('clip_empty', lang)}[/dim]")
        raise typer.Exit(0)

    cfg = load_config()
    profile = load_profile()
    notes_dir = get_notes_dir()

    async def _run() -> None:
        from neocortex.clipper import fetch_clip_content, process_clip

        # Multi-image clip: OCR each image sequentially, merge into one clip
        if multi_images:
            if not cfg.provider or not cfg.api_key:
                console.print(f"  [red]{t('clip_image_needs_llm', lang)}[/red]")
                return
            from neocortex.llm import create_provider
            from pathlib import Path as _Path
            provider = create_provider(cfg)
            media_types = {
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
            }
            parts: list[str] = []
            for idx, img_path in enumerate(multi_images, 1):
                with console.status(f"  {t('clip_image_processing_n', lang, n=str(idx), total=str(len(multi_images)))}"):
                    img_data = _Path(img_path).read_bytes()
                    suffix = _Path(img_path).suffix.lower()
                    media_type = media_types.get(suffix, "image/png")
                    try:
                        part = await provider.describe_image(
                            img_data, media_type,
                            "Please extract ALL text from this screenshot. "
                            "Transcribe verbatim. Preserve structure (headings, lists, paragraphs). "
                            "If there are non-text elements (images, charts), briefly describe them. "
                            "Output clean markdown.",
                        )
                    except Exception as e:
                        if "image_url" in str(e) or "image" in str(e).lower() and "unsupported" in str(e).lower():
                            console.print(f"  [red]{t('clip_image_no_vision', lang)}[/red]")
                            return
                        raise
                    parts.append(part)

                # Copy image to notes dir
                from neocortex.config import get_notes_dir as _get_notes_dir
                img_dest_dir = _get_notes_dir() / "images"
                img_dest_dir.mkdir(parents=True, exist_ok=True)
                import shutil
                dest = img_dest_dir / _Path(img_path).name
                if not dest.exists():
                    shutil.copy2(img_path, str(dest))

            content = "\n\n".join(parts)
            title = _Path(multi_images[0]).stem
            clip_type = "screenshot"
            clip_source = ", ".join(_Path(p).name for p in multi_images)
            # Skip to saving
            fetched = {"title": title, "content": content, "clip_type": clip_type, "source": clip_source}
        else:
            with console.status(f"  {t('clip_fetching', lang)}"):
                fetched = await fetch_clip_content(raw_input)

        # A: refuse to save when fetch produced garbage; otherwise LLM will
        # hallucinate concepts about the error page and pollute the graph.
        if fetched.get("_fetch_status") == "failed":
            from rich.markup import escape as _esc
            err = fetched.get("_fetch_error") or "unknown"
            console.print()
            console.print(f"  [red]⚠ {t('clip_fetch_failed', lang, error=_esc(err))}[/red]")
            console.print(f"  [dim]{t('clip_fetch_failed_hint', lang)}[/dim]")
            console.print()
            return

        title = fetched["title"]
        content = fetched["content"]
        clip_type = fetched["clip_type"]
        clip_source = fetched["source"]

        # Single image clip: use LLM to describe/OCR the image
        image_path = fetched.get("_image_path")
        if image_path and not content:
            if not cfg.provider or not cfg.api_key:
                console.print(f"  [red]{t('clip_image_needs_llm', lang)}[/red]")
                return
            from neocortex.llm import create_provider
            provider = create_provider(cfg)
            from pathlib import Path as _Path
            img_data = _Path(image_path).read_bytes()
            suffix = _Path(image_path).suffix.lower()
            media_types = {
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
            }
            media_type = media_types.get(suffix, "image/png")
            with console.status(f"  {t('clip_image_processing', lang)}"):
                try:
                    content = await provider.describe_image(
                        img_data, media_type,
                        "Please extract ALL text from this screenshot. "
                        "Transcribe verbatim. Preserve structure (headings, lists, paragraphs). "
                        "If there are non-text elements (images, charts), briefly describe them. "
                        "Output clean markdown.",
                    )
                except Exception as e:
                    if "image_url" in str(e) or "image" in str(e).lower() and "unsupported" in str(e).lower():
                        console.print(f"  [red]{t('clip_image_no_vision', lang)}[/red]")
                        return
                    raise
            clip_type = "screenshot"

            # Copy image to notes dir for reference
            from neocortex.config import get_notes_dir as _get_notes_dir
            img_dest_dir = _get_notes_dir() / "images"
            img_dest_dir.mkdir(parents=True, exist_ok=True)
            import shutil
            dest = img_dest_dir / _Path(image_path).name
            if not dest.exists():
                shutil.copy2(image_path, str(dest))

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
                try:
                    rel = str(note_path.relative_to(notes_dir))
                except ValueError:
                    rel = note_path.name
                note_index.index_note(rel, doc.title, full_content)

                console.print()
                return

        from neocortex.models import ClipResult

        processed = {
            "summary": "",
            "relevance": "",
            "related_concepts": [],
            "auto_tags": [],
            "topic": "general",
        }

        # Resolve effective LLM intent per Q11:
        #   process=True  → user explicitly opted in
        #   process=False → user explicitly opted out (--no-process)
        #   process=None  → config-driven default (clip_default_process)
        if process is True:
            user_wants_llm = True
        elif process is False:
            user_wants_llm = False
        else:
            user_wants_llm = cfg.clip_default_process

        # Track LLM status explicitly per §5.1 — no silent swallowing.
        llm_status = "skipped_user_opt_out"
        llm_error: str | None = None

        if user_wants_llm:
            if not (cfg.provider and cfg.api_key):
                llm_status = "skipped_no_key"
            else:
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
                    # process_clip swallows provider/JSON errors internally and
                    # returns a fallback dict with _llm_status='failed'; read
                    # that here instead of assuming success.
                    llm_status = processed.pop("_llm_status", "ok")
                    llm_error = processed.pop("_llm_error", None)
                except Exception as exc:
                    # Anything that escaped process_clip (e.g. create_provider
                    # raising on bad config) is also a real failure.
                    llm_status = "failed"
                    llm_error = str(exc) or exc.__class__.__name__

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
            try:
                rel = str(saved_path.relative_to(notes_dir))
            except ValueError:
                rel = saved_path.name
            idx.index_note(rel, clip_obj.title or raw_input[:50], clip_obj.content)
        except Exception:
            pass

        # Link clip to concept pages (boost evidence_count) and capture deltas.
        existing_cluster_delta = []
        new_or_pending_clusters: list[str] = []
        related_notes = []
        if clip_obj.related_concepts:
            existing_cluster_delta = _link_clip_to_concepts(notes_dir, clip_obj)
            new_or_pending_clusters = _compute_new_or_pending(notes_dir, clip_obj.related_concepts)
            related_notes = _find_related_notes(notes_dir, clip_obj, saved_path=saved_path)

        from neocortex.config import append_log
        append_log("clip", clip_obj.title or raw_input[:50])

        result = ClipResult(
            saved_path=str(saved_path),
            clip=clip_obj,
            llm_status=llm_status,
            llm_error=llm_error,
            existing_cluster_delta=existing_cluster_delta,
            new_or_pending_clusters=new_or_pending_clusters,
            related_notes=related_notes,
        )

        _print_clip_result(result, lang, fallback_title=raw_input[:50])

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


def _print_clip_result(result, lang: str, fallback_title: str = "") -> None:
    """Render a ClipResult to the console (structured feedback per §5.1).

    NB: all LLM-derived / user-content strings (concept names, titles, snippets)
    must go through ``rich.markup.escape`` — Rich treats ``[name]`` as a style
    tag and silently drops short ASCII tokens like ``[redis]`` / ``[abc]``,
    making the output look like the data is corrupted when it isn't.
    """
    from rich.markup import escape

    clip_obj = result.clip
    display_title = clip_obj.title or fallback_title or clip_obj.id

    console.print()
    console.print(f"  [green]{t('clip_saved', lang)}[/green]")
    console.print()
    console.print(f"  [bold]{escape(display_title)}[/bold]")
    if clip_obj.summary:
        console.print(f"  [dim]{t('clip_summary', lang)}:[/dim] {escape(clip_obj.summary)}")
    if clip_obj.related_concepts:
        concepts_str = ", ".join(escape(f"[[{c}]]") for c in clip_obj.related_concepts)
        console.print(f"  [dim]{t('clip_related', lang)}:[/dim] {concepts_str}")
    if clip_obj.relevance:
        console.print(f"  [dim]{t('clip_relevance', lang)}:[/dim] {escape(clip_obj.relevance)}")
    if clip_obj.topic:
        console.print(f"  [dim]{t('clip_topic', lang)}:[/dim] {escape(clip_obj.topic)}")

    if result.existing_cluster_delta:
        deltas_str = ", ".join(
            f"{escape(f'[[{d.concept}]]')} +1 ({d.count_before}→{d.count_after})"
            for d in result.existing_cluster_delta
        )
        console.print(f"  [green]📈 {t('clip_growing', lang)}:[/green] {deltas_str}")

    if result.new_or_pending_clusters:
        seeds_str = ", ".join(escape(f"[[{c}]]") for c in result.new_or_pending_clusters)
        hint = t("clip_seeded_hint", lang)
        console.print(
            f"  [cyan]🌱 {t('clip_seeded', lang)} ({len(result.new_or_pending_clusters)}):[/cyan] {seeds_str} [dim]{hint}[/dim]"
        )

    if result.related_notes:
        console.print(f"  [magenta]🔗 {t('clip_related_notes', lang)}:[/magenta]")
        for note in result.related_notes:
            snippet = note.snippet.strip().replace("\n", " ")
            if len(snippet) > 80:
                snippet = snippet[:80] + "…"
            label = note.title or note.filename
            line = f"     · [bold]{escape(label)}[/bold]"
            if snippet:
                line += f" [dim]— {escape(snippet)}[/dim]"
            console.print(line)

    if result.llm_status == "failed":
        console.print(
            f"  [yellow]⚠ {t('clip_llm_failed', lang, error=escape(result.llm_error or ''))}[/yellow]"
        )
    elif result.llm_status == "skipped_no_key":
        console.print(f"  [yellow]ℹ {t('clip_llm_skipped_no_key', lang)}[/yellow]")
    elif result.llm_status == "skipped_user_opt_out":
        console.print(f"  [dim]{t('clip_llm_skipped_opt_out', lang)}[/dim]")

    console.print()


def _link_clip_to_concepts(notes_dir: Path, clip_obj) -> list:
    """Link a clip's related_concepts to existing concept pages.

    Bumps evidence_count and appends source reference. Returns a list of
    ClusterDelta describing concepts whose count actually changed (used to
    feed structured feedback). Concepts without a page are silently skipped
    here — caller should pair this with _compute_new_or_pending() to surface
    those as new/pending clusters.
    """
    import os
    import re
    import tempfile
    from datetime import date as _date

    from neocortex.models import ClusterDelta

    deltas: list[ClusterDelta] = []
    concepts_dir = notes_dir / "concepts"
    if not concepts_dir.exists():
        return deltas

    for concept_name in clip_obj.related_concepts:
        slug = concept_name.strip().lower().replace(" ", "-")
        concept_path = concepts_dir / f"{slug}.md"
        if not concept_path.exists():
            continue

        try:
            content = concept_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # Check if this clip source is already referenced
        clip_ref = f"clip:{clip_obj.id}"
        if clip_ref in content:
            continue

        # Bump evidence_count
        ec_match = re.search(r"^evidence_count:\s*(\d+)", content, re.MULTILINE)
        old_count = int(ec_match.group(1)) if ec_match else 0
        new_count = old_count + 1
        if ec_match:
            content = re.sub(
                r"^evidence_count:\s*\d+",
                f"evidence_count: {new_count}",
                content,
                count=1,
                flags=re.MULTILINE,
            )

        # Update last_updated
        today = _date.today().isoformat()
        content = re.sub(
            r"^last_updated:\s*\S+",
            f"last_updated: {today}",
            content,
            count=1,
            flags=re.MULTILINE,
        )

        # Append clip reference to source notes list in frontmatter
        sn_match = re.search(r'^source_notes:\s*\[([^\]]*)\]', content, re.MULTILINE)
        if sn_match:
            existing = sn_match.group(1).strip()
            if existing:
                new_list = f'{existing}, "{clip_ref}"'
            else:
                new_list = f'"{clip_ref}"'
            content = content[:sn_match.start()] + f"source_notes: [{new_list}]" + content[sn_match.end():]

        fd, tmp_path = tempfile.mkstemp(dir=str(concepts_dir), suffix=".tmp")
        wrote = False
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, str(concept_path))
            wrote = True
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if wrote and ec_match:
            deltas.append(ClusterDelta(
                concept=concept_name,
                count_before=old_count,
                count_after=new_count,
            ))

    return deltas


def _compute_new_or_pending(notes_dir: Path, related_concepts: list[str]) -> list[str]:
    """Return concepts that don't yet have a concepts/<slug>.md page.

    Per Q14 decision (CLIENT_PROPOSAL.md v0.5), clip never auto-creates stub
    concept pages — these names are surfaced to the UI as "new topics waiting
    for kb compile" so the user gets seeding feedback on a cold-start vault.
    """
    concepts_dir = notes_dir / "concepts"
    pending: list[str] = []
    for concept_name in related_concepts:
        slug = concept_name.strip().lower().replace(" ", "-")
        if not slug:
            continue
        if not (concepts_dir / f"{slug}.md").exists():
            pending.append(concept_name)
    return pending


def _find_related_notes(
    notes_dir: Path,
    clip_obj,
    saved_path: Path | None = None,
    limit: int = 5,
) -> list:
    """Find existing notes related to this clip via FTS5 over concept names.

    Best-effort: returns empty list if the index isn't available or there
    are no concepts to query against. saved_path is used to exclude the
    freshly-saved clip itself from results.
    """
    from neocortex.config import get_data_dir
    from neocortex.models import RelatedNoteRef
    from neocortex.search import NoteIndex

    if not clip_obj.related_concepts:
        return []

    try:
        index = NoteIndex(get_data_dir() / "neocortex.sqlite")
        if not index.has_index():
            return []
    except Exception:
        return []

    own_filename = ""
    if saved_path is not None:
        try:
            own_filename = str(saved_path.relative_to(notes_dir))
        except ValueError:
            own_filename = saved_path.name

    seen: dict[str, RelatedNoteRef] = {}
    for concept_name in clip_obj.related_concepts:
        try:
            hits = index.search(concept_name, limit=limit)
        except Exception:
            continue
        for hit in hits:
            fname = hit.get("filename", "")
            if not fname or fname == own_filename:
                continue
            if fname in seen:
                continue
            seen[fname] = RelatedNoteRef(
                filename=fname,
                title=hit.get("title", "") or fname,
                snippet=hit.get("snippet", ""),
                reason=f"matched: {concept_name}",
            )
            if len(seen) >= limit:
                return list(seen.values())
    return list(seen.values())
