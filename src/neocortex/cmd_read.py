"""Read command and its helper functions."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import typer
from rich.prompt import Prompt
from rich.text import Text

from neocortex.cli import (
    _get_lang,
    _maybe_migrate_notes,
    app,
    calibrate,
    console,
)
from neocortex.i18n import t
from neocortex.models import Language, Profile, TopicRead


@app.command()
def read(
    source: str = typer.Argument(..., help="URL, PDF, or file path"),
    scan: bool = typer.Option(False, "--scan", help="Quick scan: 1-line summary + priority rating"),
    focus: str = typer.Option(None, help="Focus topic"),
    question: str = typer.Option(None, help="Question to answer"),
    audio: bool = typer.Option(False, "--audio", help="Generate audio version"),
    deep: bool = typer.Option(False, "--deep", help="Deep concept anatomy mode (8 dimensions)"),
) -> None:
    """Read a URL/file and generate personalized notes."""
    from neocortex.config import get_data_dir, get_notes_dir, load_config, load_profile, save_profile
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

    async def _run_read() -> None:
        from neocortex.reader.fetcher import ContentFetcher
        from neocortex.reader.teacher import generate_notes, generate_outline

        fetcher = ContentFetcher(provider=provider)

        with console.status(f"  {t('read_fetching', lang)}"):
            doc = await fetcher.fetch(source)

        if scan:
            with console.status(f"  {t('scan_analyzing', lang)}"):
                from neocortex.reader.teacher import generate_scan_summary

                result = await generate_scan_summary(doc, prof, provider)

            console.print()
            priority_colors = {"P0": "red bold", "P1": "yellow", "P2": "dim"}
            style = priority_colors.get(result.get("priority", "P2"), "dim")
            console.print(f"  [{style}]{result.get('priority', 'P2')}[/{style}] {result.get('summary', doc.title)}")
            if result.get("relevant_gaps"):
                gaps_str = ", ".join(result["relevant_gaps"][:5])
                console.print(f"  [dim]{t('scan_gaps', lang)}: {gaps_str}[/dim]")
            console.print()
            return

        with console.status(f"  {t('analyzing', lang)}"):
            outline = await generate_outline(doc, prof, provider)

        console.print()
        console.print(f"  [bold]{t('read_outline_title', lang, title=doc.title)}[/bold]")
        console.print("  " + "\u2501" * 52)
        console.print()

        marker_icons = {"skip": "\u2713", "brief": "\u25b3", "deep": "\u2605"}
        marker_styles = {"skip": "dim", "brief": "yellow", "deep": "bold green"}
        marker_keys = {"skip": "read_marker_skip", "brief": "read_marker_brief", "deep": "read_marker_deep"}

        for item in outline.items:
            icon = marker_icons.get(item.marker, "\u25b3")
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
        confirm = Prompt.ask(
            f"  [bold]?[/bold] {t('read_outline_confirm', lang)}",
            choices=["y", "n", "Y", "N"],
            default="y",
            console=console,
        )
        if confirm.lower() == "n":
            return

        with console.status(f"  {t('read_generating', lang)}"):
            notes_content = await generate_notes(
                doc, outline, prof, provider,
                focus=focus,
                question=question,
                deep=deep,
            )

        notes_dir = get_notes_dir()
        safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in doc.title)
        safe_title = safe_title.strip().replace(" ", "-").lower()[:60]
        if not safe_title:
            safe_title = "note"
        today = date.today().isoformat()
        filename = f"{safe_title}-{today}.md"
        note_path = notes_dir / filename
        counter = 1
        while note_path.exists():
            counter += 1
            filename = f"{safe_title}-{today}-{counter}.md"
            note_path = notes_dir / filename
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

        console.print()
        console.print(f"  [green]{t('read_saved', lang, path=str(note_path))}[/green]")

        # Render Mermaid diagrams to SVG and generate HTML companion
        from neocortex.reader.visual import generate_html_note, has_mermaid_diagrams, render_mermaid_to_svg

        if has_mermaid_diagrams(full_content):
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

        # Index the final content on disk (after all rendering/SVG overwrites)
        from neocortex.search import NoteIndex
        final_content = note_path.read_text(encoding="utf-8")
        note_index = NoteIndex(get_data_dir() / "neocortex.sqlite")
        note_index.index_note(note_path.name, doc.title, final_content)

        # Generate flashcards for spaced repetition
        import uuid as _uuid
        from neocortex.reader.teacher import generate_flashcards
        from neocortex.config import save_flashcards
        from neocortex.models import Flashcard

        try:
            with console.status(f"  {t('flashcard_generating', lang)}"):
                raw_cards = await generate_flashcards(doc, outline, notes_content, prof, provider)
            if raw_cards:
                cards = [Flashcard(
                    id=str(_uuid.uuid4())[:8],
                    source_note=note_path.name,
                    question=c["question"],
                    answer=c["answer"],
                    concept=c.get("concept", ""),
                    difficulty=c.get("difficulty", "medium"),
                    knowledge_layer=c.get("knowledge_layer", "conceptual"),
                    next_review=date.today().isoformat(),
                ) for c in raw_cards]
                save_flashcards(notes_dir, note_path.stem, cards)
                console.print(f"  [green]{t('flashcard_created', lang, count=str(len(cards)))}[/green]")
        except Exception:
            pass

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
        except Exception:
            pass

        try:
            from neocortex.compiler import compile_note
            with console.status(f"  {t('compile_updating', lang)}"):
                compile_result = await compile_note(note_path, notes_dir, prof, provider, lang)
            if compile_result.concepts_created + compile_result.concepts_updated > 0:
                console.print(f"  [green]{t('compile_done', lang, created=str(compile_result.concepts_created), updated=str(compile_result.concepts_updated))}[/green]")
            if compile_result.conflicts:
                for conflict in compile_result.conflicts:
                    conflict_type = conflict.get("type", "genuine")
                    type_key = f"conflict_{conflict_type}"
                    type_label = t(type_key, lang)
                    console.print(f"  [yellow]\u26a1 {t('conflict_detected', lang)}: {type_label}[/yellow]")
                    console.print(f"    {conflict.get('explanation', '')}")
                    hint = conflict.get("resolution_hint", "")
                    if hint:
                        console.print(f"    [dim]{hint}[/dim]")
        except Exception:
            pass

        if audio:
            from neocortex.tts import prepare_text_for_speech, text_to_speech

            audio_path = note_path.with_suffix(".mp3")
            speech_text = prepare_text_for_speech(notes_content)
            if speech_text:
                try:
                    with console.status(f"  {t('audio_generating', lang)}"):
                        await text_to_speech(speech_text, str(audio_path), lang.value)
                    console.print(f"  [green]{t('audio_saved', lang, path=str(audio_path))}[/green]")
                except RuntimeError as exc:
                    console.print(f"  [red]{t('error', lang)}: {exc}[/red]")

        if cfg.output_settings.auto_open:
            import platform
            import subprocess
            opener = "open" if platform.system() == "Darwin" else "xdg-open"
            try:
                subprocess.Popen([opener, str(note_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass

        _match_and_update_recommendations(lang, prof, source, doc.title, str(note_path))

        _collect_feedback(lang, prof, source, doc.title, focus, note_path)

        import random

        if random.random() < 0.4:
            _collect_reflection(lang, prof, note_path, provider)

    asyncio.run(_run_read())


def _match_and_update_recommendations(
    lang: Language,
    prof: Profile,
    source: str,
    title: str,
    note_path: str,
) -> None:
    """Match current read against pending recommendations and update status."""
    from neocortex.config import (
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
        status_label = {"gap": "gap", "learning": "learning", "known": "known \u2713"}
        console.print(f"  [dim]{t('recommend_gap_updated', lang, gap=gap_name, status=status_label.get(new_status, new_status))}[/dim]")

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
