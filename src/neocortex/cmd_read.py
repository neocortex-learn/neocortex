"""Read command and its helper functions."""

from __future__ import annotations

from neocortex._async import run_async
from datetime import date
from pathlib import Path

import typer
from rich.prompt import Prompt
from rich.text import Text

from neocortex.cli import (
    _maybe_migrate_notes,
    app,
    calibrate,
    console,
)
from neocortex.i18n import t
from neocortex.models import Language, Profile, TopicRead


def _resolve_topic_dir(notes_dir: Path, doc, outline, prof: Profile) -> Path:
    """Determine subdirectory based on profile domains. Falls back to 'general'."""
    known_domains = set()
    for domain_name in prof.skills.domains:
        known_domains.add(domain_name.lower())

    # 从 outline 的 deep 标记和文档标题中提取关键词
    keywords: list[str] = []
    if outline and outline.items:
        for item in outline.items:
            if item.marker == "deep":
                keywords.extend(item.title.lower().split())
    keywords.extend(doc.title.lower().replace("-", " ").replace("_", " ").split())

    # 匹配 domain
    for domain in known_domains:
        domain_words = domain.replace("_", " ").replace("-", " ").split()
        for dw in domain_words:
            if len(dw) >= 3 and any(dw in kw for kw in keywords):
                return notes_dir / domain.replace("_", "-")

    return notes_dir / "general"


def _find_duplicate_read(notes_dir: Path, source: str, force: bool) -> Path | None:
    """Mirror services/read.py: short-circuit if this URL was already deep-read.

    Saves 30s-3min and ~$0.05 per duplicate. --force bypasses dedup when
    re-reading is intentional.
    """
    if force:
        return None
    from neocortex.dedup import find_existing, normalize_source_url
    norm = normalize_source_url(source)
    if not norm:
        return None
    return find_existing(notes_dir, norm)


async def _run_scan_mode(doc, prof: Profile, provider, lang) -> None:
    """Quick scan: 1-line summary + priority rating, no notes saved."""
    from neocortex.reader.teacher import generate_scan_summary

    with console.status(f"  {t('scan_analyzing', lang)}"):
        result = await generate_scan_summary(doc, prof, provider)

    console.print()
    priority_colors = {"P0": "red bold", "P1": "yellow", "P2": "dim"}
    style = priority_colors.get(result.get("priority", "P2"), "dim")
    console.print(f"  [{style}]{result.get('priority', 'P2')}[/{style}] {result.get('summary', doc.title)}")
    if result.get("relevant_gaps"):
        gaps_str = ", ".join(result["relevant_gaps"][:5])
        console.print(f"  [dim]{t('scan_gaps', lang)}: {gaps_str}[/dim]")
    console.print()


async def _generate_and_display_outline(doc, prof: Profile, provider, lang):
    """Generate the reading outline and render it as a marker-annotated list."""
    from neocortex.reader.teacher import generate_outline

    with console.status(f"  {t('analyzing', lang)}"):
        outline = await generate_outline(doc, prof, provider)

    console.print()
    console.print(f"  [bold]{t('read_outline_title', lang, title=doc.title)}[/bold]")
    console.print("  " + "━" * 52)
    console.print()

    marker_icons = {"skip": "✓", "brief": "△", "deep": "★"}
    marker_styles = {"skip": "dim", "brief": "yellow", "deep": "bold green"}
    marker_keys = {"skip": "read_marker_skip", "brief": "read_marker_brief", "deep": "read_marker_deep"}

    for item in outline.items:
        icon = marker_icons.get(item.marker, "△")
        style = marker_styles.get(item.marker, "")
        marker_text = t(marker_keys.get(item.marker, "read_marker_brief"), lang)
        line = Text()
        line.append(f"  {icon}  ", style=style)
        line.append(f"{item.title:<40}", style=style)
        line.append(f" {marker_text}", style="dim")
        if item.reason:
            line.append(f" ({item.reason})", style="dim")
        console.print(line)

    console.print()
    return outline


def _confirm_outline(lang) -> bool:
    confirm = Prompt.ask(
        f"  [bold]?[/bold] {t('read_outline_confirm', lang)}",
        choices=["y", "n", "Y", "N"],
        default="y",
        console=console,
    )
    return confirm.lower() != "n"


def _write_read_note(
    notes_dir: Path,
    doc,
    outline,
    prof: Profile,
    notes_content: str,
    source: str,
    focus: str | None,
) -> tuple[Path, str, str]:
    """Resolve the topic dir, build frontmatter, and write the note to disk.

    Returns (note_path, full_content, safe_title).
    """
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in doc.title)
    safe_title = safe_title.strip().replace(" ", "-").lower()[:60]
    if not safe_title:
        safe_title = "note"
    today = date.today().isoformat()

    # 按 profile domain 分类存储
    topic_dir = _resolve_topic_dir(notes_dir, doc, outline, prof)
    topic_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{safe_title}-{today}.md"
    note_path = topic_dir / filename
    counter = 1
    while note_path.exists():
        counter += 1
        filename = f"{safe_title}-{today}-{counter}.md"
        note_path = topic_dir / filename

    # Build frontmatter
    frontmatter_lines = [
        "---",
        f"title: \"{doc.title.replace(chr(34), chr(39))}\"",
        f"source: \"{source.replace(chr(34), chr(39))}\"",
        f"date: {today}",
    ]
    # Add tags from outline markers
    deep_topics = [item.title for item in outline.items if item.marker == "deep"]
    if deep_topics:
        frontmatter_lines.append("tags:")
        for topic in deep_topics[:5]:
            safe_tag = topic.strip().replace(" ", "-").lower()[:30]
            if safe_tag:
                frontmatter_lines.append(f"  - {safe_tag}")
    if focus:
        frontmatter_lines.append(f"focus: \"{focus}\"")
    frontmatter_lines.append("---")
    frontmatter_lines.append("")

    full_content = "\n".join(frontmatter_lines) + notes_content
    note_path.write_text(full_content, encoding="utf-8")

    return note_path, full_content, safe_title


def _render_diagrams_and_html(
    full_content: str,
    note_path: Path,
    doc,
    source: str,
    lang,
    notes_dir: Path,
    safe_title: str,
) -> None:
    """Render Mermaid diagrams to SVG and generate the HTML companion file."""
    from neocortex.reader.visual import generate_html_note, has_mermaid_diagrams, render_mermaid_to_svg

    if not has_mermaid_diagrams(full_content):
        return

    # SVG pre-rendering: replace Mermaid blocks with inline images
    with console.status(f"  {t('read_rendering_diagrams', lang)}"):
        rendered = render_mermaid_to_svg(full_content, notes_dir, safe_title)
    if rendered != full_content:
        note_path.write_text(rendered, encoding="utf-8")
        svg_count = rendered.count("](diagrams/")
        console.print(f"  [green]{t('read_svg_saved', lang, count=str(svg_count))}[/green]")

    # HTML companion for full interactive view
    html_content = generate_html_note(full_content, doc.title, source, lang.value)
    html_path = note_path.with_suffix(".html")
    html_path.write_text(html_content, encoding="utf-8")
    console.print(f"  [green]{t('read_html_saved', lang, path=str(html_path))}[/green]")


def _index_read_note(note_path: Path, notes_dir: Path, doc) -> None:
    """Index the final content on disk (after all rendering/SVG overwrites)."""
    from neocortex.config import get_data_dir
    from neocortex.search import NoteIndex

    final_content = note_path.read_text(encoding="utf-8")
    note_index = NoteIndex(get_data_dir() / "neocortex.sqlite")
    try:
        rel = str(note_path.relative_to(notes_dir))
    except ValueError:
        rel = note_path.name
    note_index.index_note(rel, doc.title, final_content)


def _flashcard_source_note(notes_dir: Path, note_path: Path) -> str:
    """Store new-card sources as vault-relative paths when possible.

    Legacy cards only stored a basename, which becomes ambiguous when two topic
    folders contain the same filename. Keeping the fallback preserves callers
    that intentionally write outside the configured vault.
    """
    try:
        return note_path.resolve().relative_to(notes_dir.resolve()).as_posix()
    except ValueError:
        return note_path.name


async def _maybe_generate_flashcards(
    doc, outline, notes_content: str, prof: Profile, provider, notes_dir: Path, note_path: Path, lang,
) -> None:
    import uuid as _uuid

    from neocortex.config import save_flashcards
    from neocortex.models import Flashcard
    from neocortex.reader.teacher import generate_flashcards

    try:
        with console.status(f"  {t('flashcard_generating', lang)}"):
            raw_cards = await generate_flashcards(doc, outline, notes_content, prof, provider)
        if raw_cards:
            source_note = _flashcard_source_note(notes_dir, note_path)
            cards = [Flashcard(
                id=str(_uuid.uuid4())[:8],
                source_note=source_note,
                question=c["question"],
                answer=c["answer"],
                concept=c.get("concept", ""),
                difficulty=c.get("difficulty", "medium"),
                knowledge_layer=c.get("knowledge_layer", "conceptual"),
                next_review=date.today().isoformat(),
            ) for c in raw_cards]
            save_flashcards(notes_dir, note_path.stem, cards)
            console.print(f"  [green]{t('flashcard_created', lang, count=str(len(cards)))}[/green]")
    except Exception as exc:
        console.print(f"  [yellow]{t('flashcard_generate_failed', lang, error=str(exc) or exc.__class__.__name__)}[/yellow]")


async def _maybe_generate_exercises(
    doc, outline, notes_content: str, prof: Profile, provider, note_path: Path, lang,
) -> None:
    try:
        from neocortex.reader.teacher import generate_exercises
        with console.status(f"  {t('exercise_generating', lang)}"):
            exercises_content = await generate_exercises(doc, outline, notes_content, prof, provider)
        if exercises_content and exercises_content.strip():
            exercises_path = note_path.with_suffix(".exercises.md")
            ex_content = (
                f"---\ntype: exercise\nsource: \"{doc.title}\"\ndate: {date.today().isoformat()}\n---\n\n"
                f"# Exercises: {doc.title}\n\n{exercises_content}"
            )
            exercises_path.write_text(ex_content, encoding="utf-8")
            console.print(f"  [green]{t('exercise_created', lang, path=exercises_path.name)}[/green]")
    except Exception as exc:
        console.print(f"  [yellow]{t('exercise_generate_failed', lang, error=str(exc) or exc.__class__.__name__)}[/yellow]")


async def _maybe_compile_note(note_path: Path, notes_dir: Path, prof: Profile, provider, lang) -> None:
    try:
        from neocortex.compiler import compile_note
        with console.status(f"  {t('compile_updating', lang)}"):
            compile_result = await compile_note(note_path, notes_dir, prof, provider, lang)
        if compile_result.concepts_created + compile_result.concepts_updated > 0:
            console.print(
                f"  [green]{t('compile_done', lang, created=str(compile_result.concepts_created), updated=str(compile_result.concepts_updated))}[/green]"
            )
        if compile_result.conflicts:
            for conflict in compile_result.conflicts:
                conflict_type = conflict.get("type", "genuine")
                type_key = f"conflict_{conflict_type}"
                type_label = t(type_key, lang)
                console.print(f"  [yellow]⚡ {t('conflict_detected', lang)}: {type_label}[/yellow]")
                console.print(f"    {conflict.get('explanation', '')}")
                hint = conflict.get("resolution_hint", "")
                if hint:
                    console.print(f"    [dim]{hint}[/dim]")
    except Exception as exc:
        console.print(f"  [yellow]{t('compile_failed', lang, error=str(exc) or exc.__class__.__name__)}[/yellow]")


async def _maybe_generate_audio(notes_content: str, note_path: Path, lang) -> None:
    from neocortex.tts import prepare_text_for_speech, text_to_speech

    audio_path = note_path.with_suffix(".mp3")
    speech_text = prepare_text_for_speech(notes_content)
    if not speech_text:
        return
    try:
        with console.status(f"  {t('audio_generating', lang)}"):
            await text_to_speech(speech_text, str(audio_path), lang.value)
        console.print(f"  [green]{t('audio_saved', lang, path=str(audio_path))}[/green]")
    except RuntimeError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")


def _maybe_auto_open(note_path: Path, cfg) -> None:
    if not cfg.output_settings.auto_open:
        return
    import platform
    import subprocess
    opener = "open" if platform.system() == "Darwin" else "xdg-open"
    try:
        subprocess.Popen([opener, str(note_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


async def _run_post_save_steps(
    doc, outline, notes_content: str, prof: Profile, provider, notes_dir: Path, note_path: Path, lang, cfg,
    flashcards: bool, exercises: bool, compile: bool, full: bool, audio: bool,
    source: str, focus: str | None,
) -> None:
    """Optional post-save steps (flashcards/exercises/compile/audio/auto-open),
    then logging, recommendation matching, feedback, and reflection collection."""
    do_flashcards = flashcards or full
    do_exercises = exercises or full
    do_compile = compile or full

    if do_flashcards:
        await _maybe_generate_flashcards(doc, outline, notes_content, prof, provider, notes_dir, note_path, lang)

    if do_exercises:
        await _maybe_generate_exercises(doc, outline, notes_content, prof, provider, note_path, lang)

    if do_compile:
        await _maybe_compile_note(note_path, notes_dir, prof, provider, lang)

    if audio:
        await _maybe_generate_audio(notes_content, note_path, lang)

    _maybe_auto_open(note_path, cfg)

    from neocortex.config import append_log
    append_log("read", doc.title)

    _match_and_update_recommendations(lang, prof, source, doc.title, str(note_path))

    _collect_feedback(lang, prof, source, doc.title, focus, note_path)

    import random

    if random.random() < 0.4:
        _collect_reflection(lang, prof, note_path, provider)


async def _run_read_pipeline(
    source: str,
    scan: bool,
    focus: str | None,
    question: str | None,
    audio: bool,
    deep: bool,
    yes: bool,
    flashcards: bool,
    exercises: bool,
    compile: bool,
    full: bool,
    force: bool,
    lang,
    prof: Profile,
    provider,
    cfg,
) -> None:
    from neocortex.config import get_notes_dir
    from neocortex.reader.fetcher import ContentFetcher
    from neocortex.reader.teacher import generate_notes

    notes_dir = get_notes_dir()

    existing = _find_duplicate_read(notes_dir, source, force)
    if existing:
        console.print(f"  [yellow]{t('read_reused', lang, path=str(existing))}[/yellow]")
        return

    fetcher = ContentFetcher(provider=provider)

    with console.status(f"  {t('read_fetching', lang)}"):
        doc = await fetcher.fetch(source)

    if scan:
        await _run_scan_mode(doc, prof, provider, lang)
        return

    outline = await _generate_and_display_outline(doc, prof, provider, lang)

    if not yes and not _confirm_outline(lang):
        return

    with console.status(f"  {t('read_generating', lang)}"):
        notes_content = await generate_notes(
            doc, outline, prof, provider,
            focus=focus,
            question=question,
            deep=deep,
        )

    notes_dir = get_notes_dir()
    note_path, full_content, safe_title = _write_read_note(
        notes_dir, doc, outline, prof, notes_content, source, focus,
    )

    console.print()
    console.print(f"  [green]{t('read_saved', lang, path=str(note_path))}[/green]")

    _render_diagrams_and_html(full_content, note_path, doc, source, lang, notes_dir, safe_title)

    _index_read_note(note_path, notes_dir, doc)

    # Optional steps — only run when explicitly requested
    await _run_post_save_steps(
        doc, outline, notes_content, prof, provider, notes_dir, note_path, lang, cfg,
        flashcards, exercises, compile, full, audio, source, focus,
    )


@app.command()
def read(
    source: str = typer.Argument(..., help="URL, PDF, or file path"),
    scan: bool = typer.Option(False, "--scan", help="Quick scan: 1-line summary + priority rating"),
    focus: str = typer.Option(None, help="Focus topic"),
    question: str = typer.Option(None, help="Question to answer"),
    audio: bool = typer.Option(False, "--audio", help="Generate audio version"),
    deep: bool = typer.Option(False, "--deep", help="Deep concept anatomy mode (8 dimensions)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip outline confirmation"),
    flashcards: bool = typer.Option(False, "--flashcards", help="Generate flashcards (adds ~30s)"),
    exercises: bool = typer.Option(False, "--exercises", help="Generate exercises (adds ~30s)"),
    compile: bool = typer.Option(False, "--compile", help="Compile into concept graph (adds ~1-3min)"),
    full: bool = typer.Option(False, "--full", help="Enable all: flashcards + exercises + compile"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过 URL 去重，强制重读重存"),
) -> None:
    """Read a URL/file and generate personalized notes."""
    from neocortex.config import load_config, load_profile
    from neocortex.llm import create_provider

    cfg = load_config()
    lang = cfg.output_settings.language
    prof = load_profile()
    _maybe_migrate_notes()

    try:
        provider = create_provider(cfg)
    except ValueError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
        raise typer.Exit(1)

    run_async(_run_read_pipeline(
        source, scan, focus, question, audio, deep, yes, flashcards, exercises, compile, full, force,
        lang, prof, provider, cfg,
    ))


def _match_and_update_recommendations(
    lang: Language,
    prof: Profile,
    source: str,
    title: str,
    note_path: str,
) -> None:
    """Match current read against pending recommendations and update status."""
    from neocortex.config import (
        load_gap_progress,
        load_recommendations,
        save_profile,
        save_recommendations,
        update_gap_status,
    )
    from neocortex.tracker import expire_stale_recommendations, match_recommendation

    all_records = load_recommendations()
    if not all_records:
        return

    all_records = expire_stale_recommendations(all_records)

    pending = [r for r in all_records if r.status == "pending"]
    if not pending:
        save_recommendations(all_records)
        return

    matched = match_recommendation(source, title, pending)

    if matched is None and pending:
        # Show up to 3 pending recommendations, let user pick or skip
        shown = pending[:3]
        console.print()
        for i, rec in enumerate(shown, 1):
            console.print(f"    [dim]{i})[/dim] {rec.topic}")
        answer = Prompt.ask(
            f"  [bold]?[/bold] {t('recommend_match_confirm', lang, topic=shown[0].topic)}  [dim](1-{len(shown)}/n)[/dim]",
            default="n",
            console=console,
        )
        if answer.isdigit() and 1 <= int(answer) <= len(shown):
            matched = shown[int(answer) - 1]

    if matched is None:
        save_recommendations(all_records)
        return

    from datetime import date as _date

    matched.status = "completed"
    matched.completed_at = _date.today().isoformat()
    matched.notes_generated.append(note_path)

    console.print(f"  [green]{t('recommend_match_found', lang, topic=matched.topic)}[/green]")

    for gap_name in matched.related_gaps:
        new_status = update_gap_status(gap_name, prof)
        status_label = {"gap": "gap", "learning": "learning", "verified": "verified ✓", "known": "known ✓✓"}
        console.print(f"  [dim]{t('recommend_gap_updated', lang, gap=gap_name, status=status_label.get(new_status, new_status))}[/dim]")
        if new_status == "learning":
            gap_progress = load_gap_progress()
            entry = gap_progress.get(gap_name)
            if entry and entry.reads >= 2:
                console.print(f"  [yellow]{t('gap_needs_verification', lang, gap=gap_name)}[/yellow]")

    save_recommendations(all_records)
    if matched.related_gaps:
        save_profile(prof)


def _collect_feedback(
    lang: Language,
    prof: Profile,
    source: str,
    title: str,
    focus: str | None,
    note_path: Path,
) -> None:
    from neocortex.config import save_profile

    console.print()
    feedback_options = {
        "1": "too_easy",
        "2": "just_right",
        "3": "too_hard",
        "4": "skip",
    }
    prompt_text = (
        f"  [bold]?[/bold] {t('feedback_prompt', lang)}  "
        f"[1] {t('feedback_too_easy', lang)}  "
        f"[2] {t('feedback_just_right', lang)}  "
        f"[3] {t('feedback_too_hard', lang)}  "
        f"[4] {t('feedback_skip', lang)}"
    )
    answer = Prompt.ask(prompt_text, choices=["1", "2", "3", "4"], default="4", console=console)
    feedback_value = feedback_options[answer]

    if feedback_value != "skip":
        prof.calibration = calibrate(feedback_value, prof.calibration)

    topic_entry = TopicRead(
        source=source,
        title=title,
        date=date.today().isoformat(),
        focus=focus,
        feedback=feedback_value if feedback_value != "skip" else None,
    )
    prof.learning_history.topics_read.append(topic_entry)

    if focus:
        normalized_focus = focus.lower().replace(" ", "_")
        freq = prof.learning_history.topic_frequency
        freq[normalized_focus] = freq.get(normalized_focus, 0) + 1

    save_profile(prof)


def _collect_reflection(
    lang: Language,
    prof: Profile,
    note_path: Path,
    provider: object,
) -> None:
    """Collect 3 structured micro-reflection prompts after reading."""
    from neocortex.compiler import collect_all_concepts
    from neocortex.config import get_notes_dir

    notes_dir = get_notes_dir()
    concepts = collect_all_concepts(notes_dir / "concepts")
    concept_name: str | None = None
    if concepts:
        import random as _rand

        concept_name = _rand.choice(concepts).name

    console.print()
    console.print(f"  [bold]{t('reflect_title', lang)}[/bold]")
    console.print()

    skip_hint = f" [dim]{t('reflect_skip_hint', lang)}[/dim]"

    surprise = Prompt.ask(
        f"  [bold]1.[/bold] {t('reflect_surprise', lang)}{skip_hint}",
        default="",
        console=console,
    )

    if concept_name:
        connection_prompt = t("reflect_connection", lang, concept=concept_name)
    else:
        connection_prompt = t("reflect_connection", lang, concept="your prior knowledge")
    connection = Prompt.ask(
        f"  [bold]2.[/bold] {connection_prompt}{skip_hint}",
        default="",
        console=console,
    )

    application = Prompt.ask(
        f"  [bold]3.[/bold] {t('reflect_application', lang)}{skip_hint}",
        default="",
        console=console,
    )

    reflection: dict[str, str] = {}
    if surprise.strip():
        reflection["surprise"] = surprise.strip()
    if connection.strip():
        reflection["connection"] = connection.strip()
    if application.strip():
        reflection["application"] = application.strip()

    if not reflection:
        return

    _write_reflection_to_frontmatter(note_path, reflection)
    console.print(f"  [green]{t('reflect_saved', lang)}[/green]")
    console.print()


def _write_reflection_to_frontmatter(note_path: Path, reflection: dict[str, str]) -> None:
    """Insert a ``reflection`` block into the note's YAML frontmatter."""
    import os
    import tempfile

    content = note_path.read_text(encoding="utf-8")
    lines = content.split("\n")

    end_idx: int | None = None
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break

    if end_idx is None:
        return

    if not reflection:
        return

    reflection_lines: list[str] = ["reflection:"]
    for key in ("surprise", "connection", "application"):
        if key in reflection:
            escaped = reflection[key].replace('"', '\\"')
            reflection_lines.append(f'  {key}: "{escaped}"')

    new_lines = lines[:end_idx] + reflection_lines + lines[end_idx:]
    new_content = "\n".join(new_lines)

    fd, tmp_path = tempfile.mkstemp(dir=str(note_path.parent), suffix=".tmp")
    closed = False
    try:
        os.write(fd, new_content.encode("utf-8"))
        os.close(fd)
        closed = True
        os.replace(tmp_path, str(note_path))
    except Exception:
        if not closed:
            os.close(fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
