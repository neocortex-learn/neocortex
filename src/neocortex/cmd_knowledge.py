"""Knowledge base commands: notes, card, index, ask, chat."""

from __future__ import annotations

from neocortex._async import run_async
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
    kb_app,
)
from neocortex.i18n import t


@kb_app.command()
def notes(
    search: str = typer.Option(None, help="Search notes"),
    open_note: bool = typer.Option(False, "--open", help="Open matched note in editor"),
) -> None:
    """List or search your knowledge base."""
    from neocortex.config import get_notes_dir

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


@kb_app.command()
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
        success = run_async(render_card_to_png(html_path, png_path))

    if success:
        console.print(f"  [green]{t('card_saved', lang, path=str(png_path))}[/green]")
        _open_file(png_path, lang)
    else:
        console.print(f"  [yellow]{t('card_html_only', lang, path=str(html_path))}[/yellow]")
        console.print(f"  [dim]{t('card_install_playwright', lang)}[/dim]")


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
    question: str = typer.Argument(None, help="Your question"),
    chat: bool = typer.Option(False, "--chat", help="Start multi-turn chat"),
    save: bool = typer.Option(False, "--save", help="Save answer to knowledge base"),
) -> None:
    """Ask a question (or start a chat session with --chat)."""
    if chat:
        _run_chat()
        return

    if not question:
        console.print("  Usage: neocortex ask <question> or neocortex ask --chat")
        raise typer.Exit(1)

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

    answer = run_async(_run())

    console.print()
    from rich.markdown import Markdown
    console.print(Markdown(answer))
    console.print()

    from neocortex.config import append_log
    append_log("ask", question[:80])

    # Auto-evaluate whether this answer is worth saving
    should_save = save

    if not should_save:
        async def _evaluate() -> bool:
            from neocortex.asker import evaluate_insight_value
            with console.status(f"  {t('insight_evaluating', lang)}"):
                return await evaluate_insight_value(question, answer, provider)

        try:
            should_save = run_async(_evaluate())
        except Exception as exc:
            should_save = False
            console.print(f"  [dim]{t('insight_evaluate_failed', lang, error=str(exc) or exc.__class__.__name__)}[/dim]")

    if should_save:
        from neocortex.asker import save_insight

        insight_path = save_insight(question, answer, lang)
        console.print(f"  [green]{t('insight_saved', lang, path=str(insight_path))}[/green]")
        append_log("insight", question[:80])

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
            run_async(_compile_insight())
        except Exception:
            pass


def _run_chat() -> None:
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
            answer = run_async(_send(stripped))
        except KeyboardInterrupt:
            console.print("\n")
            continue

        console.print()
        console.print(Markdown(answer))
        console.print()

    non_system = [m for m in session.history if m["role"] != "system"]
    if len(non_system) >= 2:
        # Auto-evaluate which Q&A pairs are worth saving
        from neocortex.asker import evaluate_insight_value, save_insight
        from neocortex.config import append_log

        pairs: list[tuple[str, str]] = []
        for msg in non_system:
            if msg["role"] == "user":
                pairs.append((msg["content"], ""))
            elif msg["role"] == "assistant" and pairs and not pairs[-1][1]:
                q, _ = pairs[-1]
                pairs[-1] = (q, msg["content"])

        saved_count = 0
        eval_failed_count = 0

        async def _save_valuable_pairs() -> int:
            nonlocal eval_failed_count
            count = 0
            for question, answer in pairs:
                if not answer:
                    continue
                try:
                    worthy = await evaluate_insight_value(question, answer, provider)
                except Exception:
                    worthy = False
                    eval_failed_count += 1
                if worthy:
                    path = save_insight(question, answer, lang)
                    console.print(f"  [green]{t('insight_saved', lang, path=str(path))}[/green]")
                    append_log("insight", question[:80])
                    count += 1
            return count

        with console.status(f"  {t('insight_evaluating', lang)}"):
            try:
                saved_count = run_async(_save_valuable_pairs())
            except Exception as exc:
                console.print(f"  [dim]{t('insight_evaluate_failed', lang, error=str(exc) or exc.__class__.__name__)}[/dim]")

        if eval_failed_count > 0:
            console.print(f"  [dim]{t('insight_evaluate_failed', lang, error=f'{eval_failed_count} pair(s)')}[/dim]")
        if saved_count > 0:
            console.print(f"  [dim]{t('insight_auto_saved', lang, count=str(saved_count))}[/dim]")
        console.print()


@app.command()
def review(
    count: int = typer.Option(20, help="Max cards per session"),
    mode: str = typer.Option("default", help="Mode: default, diagnostic, drill, hard"),
) -> None:
    """Review flashcards with spaced repetition (SM-2)."""
    from datetime import timedelta

    from rich.panel import Panel
    from rich.markdown import Markdown

    from neocortex.config import get_notes_dir
    from neocortex.models import ReviewStats
    from neocortex.reviewer import get_review_session, is_active
    from neocortex.services.review import (
        CardNotFoundError,
        grade_card,
        load_stored_cards,
        log_review_summary,
    )

    lang = _get_lang()
    notes_dir = get_notes_dir()

    if mode not in ("default", "diagnostic", "drill", "hard"):
        console.print(f"  [red]Invalid mode '{mode}'. Valid: default, diagnostic, drill, hard[/red]")
        raise typer.Exit(1)

    stored_cards = load_stored_cards(notes_dir)
    all_cards = [s.card for s in stored_cards if is_active(s.card)]
    session_cards = get_review_session(all_cards, max_cards=count, mode=mode)

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

        # 评分 / 原子写回原存储文件 / 标准卡 concept boost 全在共享 service
        # 里完成（含跨进程锁）；Typer 层只负责交互。
        try:
            grade_card(notes_dir, card.id, quality)
        except CardNotFoundError:
            console.print(f"  [red]card {card.id} disappeared from storage, skipped[/red]")
            stats.skipped += 1
            console.print()
            continue

        stats.cards_reviewed += 1
        if quality >= 3:
            stats.correct += 1
        else:
            stats.incorrect += 1

        console.print()

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    # 重新从磁盘读：评分已由 service 落盘，内存里的 session 卡是旧快照。
    refreshed = [s.card for s in load_stored_cards(notes_dir) if is_active(s.card)]
    tomorrow_due = sum(
        1 for c in refreshed
        if c.next_review and c.next_review <= tomorrow
    )

    log_review_summary(stats.cards_reviewed, stats.correct)

    console.print(f"  [bold green]{t('review_done', lang)}[/bold green]")
    console.print(f"  {t('review_stats', lang, reviewed=str(stats.cards_reviewed), correct=str(stats.correct), tomorrow=str(tomorrow_due))}")
    rel_count = sum(1 for c in session_cards if c.card_type == "relationship")
    if rel_count > 0:
        console.print(f"  [dim]({rel_count} {t('review_relationship', lang)})[/dim]")
    console.print()


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
