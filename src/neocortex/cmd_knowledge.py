"""Knowledge base commands: notes, card, index, ask, chat."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import typer
from rich.prompt import Prompt
from rich.table import Table

from neocortex.cli import (
    _get_lang,
    _maybe_migrate_notes,
    _open_file,
    app,
    console,
)
from neocortex.i18n import t
from neocortex.models import Language


@app.command()
def notes(
    search: str = typer.Option(None, help="Search notes"),
    open_note: bool = typer.Option(False, "--open", help="Open matched note in editor"),
) -> None:
    """List or search your knowledge base."""
    from neocortex.config import get_data_dir, get_notes_dir

    lang = _get_lang()
    _maybe_migrate_notes()
    notes_dir = get_notes_dir()

    md_files = sorted(
        (f for f in notes_dir.rglob("*.md") if "diagrams" not in f.parts),
        key=lambda f: f.stat().st_mtime, reverse=True,
    )

    if not md_files:
        console.print(f"  {t('notes_empty', lang)}")
        return

    if search:
        fts_results = _fts_search(search)
        if fts_results is not None:
            if not fts_results:
                console.print(f"  {t('notes_no_match', lang, query=search)}")
                return

            console.print()
            console.print(f"  [bold]{t('search_result', lang, query=search)}[/bold]")
            console.print("  " + "\u2501" * 52)
            console.print()

            table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
            table.add_column("File", style="cyan")
            table.add_column("Title")
            table.add_column("Snippet", style="dim")

            for r in fts_results:
                snippet = r["snippet"].replace(">>>", "[bold yellow]").replace("<<<", "[/bold yellow]")
                table.add_row(r["filename"], r["title"], snippet)

            console.print(table)
            console.print()

            if open_note and fts_results:
                target = notes_dir / fts_results[0]["filename"]
                if target.exists():
                    _open_file(target, lang)

            return

        query = search.lower()
        matched: list[Path] = []
        for f in md_files:
            if query in f.name.lower():
                matched.append(f)
                continue
            try:
                content = f.read_text(encoding="utf-8")
                if query in content.lower():
                    matched.append(f)
            except (UnicodeDecodeError, OSError):
                continue

        if not matched:
            console.print(f"  {t('notes_no_match', lang, query=search)}")
            return
        md_files = matched

    console.print()
    console.print(f"  [bold]{t('notes_title', lang)}[/bold]")
    console.print("  " + "\u2501" * 52)
    console.print(f"  [dim]{t('notes_dir_info', lang, path=str(notes_dir))}[/dim]")
    console.print()

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("File", style="cyan")
    table.add_column("Date", style="dim")
    table.add_column("Size", style="dim", justify="right")

    for f in md_files:
        mtime = date.fromtimestamp(f.stat().st_mtime).isoformat()
        size_kb = f.stat().st_size / 1024
        size_str = f"{size_kb:.1f} KB"
        table.add_row(f.name, mtime, size_str)

    console.print(table)
    console.print()

    if open_note and md_files:
        _open_file(md_files[0], lang)


@app.command()
def card(
    note_path: str = typer.Argument(None, help="Path to note file (default: latest note)"),
    theme: str = typer.Option("dark", help="Theme: dark or light"),
) -> None:
    """Generate a visual card (PNG) from a note."""
    from neocortex.config import get_notes_dir
    from neocortex.reader.card import generate_card_html, render_card_to_png

    lang = _get_lang()
    notes_dir = get_notes_dir()

    if note_path:
        target = Path(note_path)
    else:
        md_files = sorted(
            (f for f in notes_dir.rglob("*.md") if "diagrams" not in f.parts),
            key=lambda f: f.stat().st_mtime, reverse=True,
        )
        if not md_files:
            console.print(f"  {t('notes_empty', lang)}")
            return
        target = md_files[0]

    if not target.exists():
        console.print(f"  [red]{t('error', lang)}: File not found: {target}[/red]")
        raise typer.Exit(1)

    content = target.read_text(encoding="utf-8")

    # Extract title from frontmatter or first heading
    import re as _re
    title_match = _re.search(r'^title:\s*"?(.+?)"?\s*$', content, _re.MULTILINE)
    if not title_match:
        title_match = _re.search(r"^#\s+(.+)$", content, _re.MULTILINE)
    title = title_match.group(1).strip() if title_match else target.stem

    source_match = _re.search(r'^source:\s*"?(.+?)"?\s*$', content, _re.MULTILINE)
    source = source_match.group(1).strip() if source_match else ""

    today = date.today().isoformat()

    with console.status(f"  {t('card_generating', lang)}"):
        html = generate_card_html(content, title, source, today, lang.value, theme)
        html_path = target.with_suffix(".card.html")
        html_path.write_text(html, encoding="utf-8")

        png_path = target.with_suffix(".card.png")
        success = asyncio.run(render_card_to_png(html_path, png_path))

    if success:
        console.print(f"  [green]{t('card_saved', lang, path=str(png_path))}[/green]")
        _open_file(png_path, lang)
    else:
        console.print(f"  [yellow]{t('card_html_only', lang, path=str(html_path))}[/yellow]")
        console.print(f"  [dim]{t('card_install_playwright', lang)}[/dim]")


@app.command()
def index() -> None:
    """Build or rebuild the note search index (FTS5 + embeddings)."""
    from neocortex.config import get_data_dir, get_notes_dir
    from neocortex.search import NoteIndex

    lang = _get_lang()
    notes_dir = get_notes_dir()
    db_path = get_data_dir() / "neocortex.sqlite"
    note_index = NoteIndex(db_path)

    with console.status(f"  {t('index_building', lang)}"):
        count = note_index.index_all(notes_dir)

    console.print(f"  [green]{t('index_done', lang, count=str(count))}[/green]")

    if note_index.has_embeddings():
        console.print(f"  [green]{t('index_embedding_done', lang)}[/green]")
    else:
        console.print(f"  [dim]{t('index_embedding_skip', lang)}[/dim]")


@app.command()
def ask(
    question: str = typer.Argument(..., help="Your question"),
    save: bool = typer.Option(False, "--save", help="Save answer to knowledge base"),
) -> None:
    """Ask a question with your skill profile as context."""
    from neocortex.config import get_notes_dir, load_config, load_profile
    from neocortex.llm import create_provider
    from neocortex.asker import ask_question

    cfg = load_config()
    prof = load_profile()
    lang = _get_lang()

    if not prof.skills.languages and not prof.skills.domains:
        console.print(f"  {t('profile_empty', lang)}")
        raise typer.Exit(1)

    try:
        provider = create_provider(cfg)
    except ValueError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
        raise typer.Exit(1)

    async def _run() -> str:
        with console.status(f"  {t('ask_thinking', lang)}"):
            return await ask_question(question, prof, provider, lang)

    answer = asyncio.run(_run())

    console.print()
    from rich.markdown import Markdown
    console.print(Markdown(answer))
    console.print()

    should_save = save
    if not should_save:
        save_answer = Prompt.ask(
            f"  [bold]?[/bold] {t('insight_save_prompt', lang)}",
            choices=["y", "n"],
            default="n",
            console=console,
        )
        should_save = save_answer.lower() == "y"

    if should_save:
        from neocortex.asker import save_insight

        insight_path = save_insight(question, answer, lang)
        console.print(f"  [green]{t('insight_saved', lang, path=str(insight_path))}[/green]")

        async def _compile_insight() -> None:
            try:
                from neocortex.compiler import compile_note
                notes_dir = get_notes_dir()
                with console.status(f"  {t('compile_updating', lang)}"):
                    result = await compile_note(insight_path, notes_dir, prof, provider, lang)
                if result.concepts_created + result.concepts_updated > 0:
                    console.print(f"  [green]{t('compile_done', lang, created=str(result.concepts_created), updated=str(result.concepts_updated))}[/green]")
            except Exception:
                pass

        try:
            asyncio.run(_compile_insight())
        except Exception:
            pass


@app.command()
def chat() -> None:
    """Start an interactive multi-turn Q&A session with your profile as context."""
    from rich.markdown import Markdown

    from neocortex.asker import ChatSession
    from neocortex.config import load_config, load_profile
    from neocortex.llm import create_provider

    cfg = load_config()
    prof = load_profile()
    lang = _get_lang()

    if not prof.skills.languages and not prof.skills.domains:
        console.print(f"  {t('profile_empty', lang)}")
        raise typer.Exit(1)

    try:
        provider = create_provider(cfg)
    except ValueError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
        raise typer.Exit(1)

    session = ChatSession(prof, provider, lang)
    empty_count = 0

    console.print()
    console.print(f"  [bold]{t('chat_welcome', lang)}[/bold]")
    console.print(f"  [dim]{t('chat_profile_loaded', lang)}[/dim]")
    console.print()

    async def _send(msg: str) -> str:
        with console.status(f"  {t('ask_thinking', lang)}"):
            return await session.send(msg)

    while True:
        try:
            user_input = Prompt.ask(f"  [bold cyan]{t('chat_prompt', lang)}[/bold cyan]", console=console)
        except KeyboardInterrupt:
            console.print()
            console.print(f"  {t('chat_goodbye', lang)}")
            break

        stripped = user_input.strip()

        if stripped.lower() in ("exit", "quit"):
            console.print(f"  {t('chat_goodbye', lang)}")
            break

        if not stripped:
            empty_count += 1
            if empty_count >= 2:
                console.print(f"  {t('chat_goodbye', lang)}")
                break
            continue

        empty_count = 0

        try:
            answer = asyncio.run(_send(stripped))
        except KeyboardInterrupt:
            console.print("\n")
            continue

        console.print()
        console.print(Markdown(answer))
        console.print()

    non_system = [m for m in session.history if m["role"] != "system"]
    if len(non_system) >= 2:
        save_answer = Prompt.ask(
            f"  [bold]?[/bold] {t('insight_save_chat', lang)}",
            choices=["y", "n"],
            default="n",
            console=console,
        )
        if save_answer.lower() == "y":
            from neocortex.asker import save_chat_insights

            paths = save_chat_insights(non_system, lang)
            for p in paths:
                console.print(f"  [green]{t('insight_saved', lang, path=str(p))}[/green]")


@app.command()
def review(
    count: int = typer.Option(20, help="Max cards per session"),
) -> None:
    """Review flashcards with spaced repetition (SM-2)."""
    from datetime import timedelta

    from rich.panel import Panel
    from rich.markdown import Markdown

    from neocortex.config import get_notes_dir, load_flashcards, save_flashcards
    from neocortex.models import Flashcard, ReviewStats
    from neocortex.reviewer import get_review_session, sm2_update

    lang = _get_lang()
    notes_dir = get_notes_dir()

    all_cards = load_flashcards(notes_dir)
    session_cards = get_review_session(all_cards, max_cards=count)

    console.print()
    console.print(f"  [bold]{t('review_title', lang)}[/bold]")
    console.print("  " + "\u2501" * 52)
    console.print()

    if not session_cards:
        total = len(all_cards)
        console.print(f"  {t('review_empty', lang)}")
        if all_cards:
            console.print(f"  {t('review_total', lang, total=str(total), due='0')}")
            next_dates = sorted(c.next_review for c in all_cards if c.next_review)
            if next_dates:
                console.print(f"  {t('review_next', lang, date=next_dates[0])}")
        console.print()
        return

    stats = ReviewStats(date=date.today().isoformat())
    total_session = len(session_cards)

    cards_by_note: dict[str, list[Flashcard]] = {}
    for c in all_cards:
        stem = Path(c.source_note).stem
        cards_by_note.setdefault(stem, []).append(c)

    for i, card in enumerate(session_cards, 1):
        console.print(f"  [dim]{t('review_progress', lang, current=str(i), total=str(total_session))}[/dim]")
        console.print()

        layer_key = {
            "factual": "review_layer_fact",
            "conceptual": "review_layer_concept",
            "procedural": "review_layer_procedure",
        }.get(card.knowledge_layer, "review_layer_concept")
        layer_tag = t(layer_key, lang)
        type_tag = f"{t('review_relationship', lang)} " if card.card_type == "relationship" else ""
        source_info = card.source_note or card.concept

        console.print(Panel(
            f"[bold]{card.question}[/bold]",
            title=f"[cyan]{t('review_question', lang)}[/cyan]",
            subtitle=f"[dim]{type_tag}{layer_tag} {t('review_source', lang)}: {source_info}[/dim]",
            border_style="cyan",
            padding=(1, 2),
        ))

        try:
            Prompt.ask(f"  [dim]{t('review_reveal', lang)}[/dim]", default="", console=console)
        except KeyboardInterrupt:
            console.print()
            break

        console.print(Panel(
            Markdown(card.answer),
            title=f"[green]{t('review_answer', lang)}[/green]",
            border_style="green",
            padding=(1, 2),
        ))

        rate_prompt = (
            f"  [bold]?[/bold] {t('review_rate', lang)}:  "
            f"[1] {t('review_rate_1', lang)}  "
            f"[2] {t('review_rate_2', lang)}  "
            f"[3] {t('review_rate_3', lang)}  "
            f"[4] {t('review_rate_4', lang)}  "
            f"[5] {t('review_rate_5', lang)}"
        )
        try:
            answer = Prompt.ask(rate_prompt, choices=["1", "2", "3", "4", "5"], default="3", console=console)
        except KeyboardInterrupt:
            console.print()
            break

        quality_map = {"1": 0, "2": 1, "3": 3, "4": 4, "5": 5}
        quality = quality_map[answer]

        sm2_update(card, quality)

        if quality >= 3 and card.concept:
            _boost_concept_confidence(notes_dir, card.concept)

        stats.cards_reviewed += 1
        if quality >= 3:
            stats.correct += 1
        else:
            stats.incorrect += 1

        note_stem = Path(card.source_note).stem
        if note_stem in cards_by_note:
            save_flashcards(notes_dir, note_stem, cards_by_note[note_stem])

        console.print()

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    tomorrow_due = sum(
        1 for c in all_cards
        if c.next_review and c.next_review <= tomorrow
    )

    console.print(f"  [bold green]{t('review_done', lang)}[/bold green]")
    console.print(f"  {t('review_stats', lang, reviewed=str(stats.cards_reviewed), correct=str(stats.correct), tomorrow=str(tomorrow_due))}")
    rel_count = sum(1 for c in session_cards if c.card_type == "relationship")
    if rel_count > 0:
        console.print(f"  [dim]({rel_count} {t('review_relationship', lang)})[/dim]")
    console.print()


def _boost_concept_confidence(notes_dir: Path, concept_name: str) -> None:
    """Boost a concept's confidence after a successful review."""
    import re as _re

    from neocortex.decay import REVIEW_BOOST, boost_confidence, decayed_confidence

    slug = concept_name.strip().lower().replace(" ", "-")
    concept_path = notes_dir / "concepts" / f"{slug}.md"
    if not concept_path.exists():
        return

    try:
        content = concept_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    conf_match = _re.search(r"^confidence:\s*([\d.]+)", content, _re.MULTILINE)
    date_match = _re.search(r"^last_updated:\s*(\S+)", content, _re.MULTILINE)
    if not conf_match:
        return

    old_conf = float(conf_match.group(1))
    old_date = date_match.group(1) if date_match else ""
    current = decayed_confidence(old_conf, old_date)
    new_conf = boost_confidence(current, REVIEW_BOOST)
    today = date.today().isoformat()

    content = _re.sub(
        r"^confidence:\s*[\d.]+",
        f"confidence: {new_conf:.4f}",
        content,
        count=1,
        flags=_re.MULTILINE,
    )
    content = _re.sub(
        r"^last_updated:\s*\S+",
        f"last_updated: {today}",
        content,
        count=1,
        flags=_re.MULTILINE,
    )

    import os
    import tempfile

    fd, tmp_path = tempfile.mkstemp(dir=str(concept_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(concept_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _fts_search(query: str) -> list[dict] | None:
    """Try hybrid search (FTS5 + vector) if embeddings exist, otherwise pure FTS5.

    Returns *None* if no index is available at all.
    """
    from neocortex.config import get_data_dir
    from neocortex.search import NoteIndex

    db_path = get_data_dir() / "neocortex.sqlite"
    if not db_path.exists():
        return None
    note_index = NoteIndex(db_path)
    if not note_index.has_index():
        return None
    try:
        if note_index.has_embeddings():
            return note_index.hybrid_search(query)
        return note_index.search(query)
    except Exception:
        return None
