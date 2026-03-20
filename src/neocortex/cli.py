"""CLI entry point for Neocortex — all commands and terminal interactions."""

from __future__ import annotations

import asyncio
import json as json_lib
import sys
from datetime import date
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from neocortex.i18n import t
from neocortex.models import (
    Calibration,
    ExperienceRange,
    Language,
    LearningGoal,
    LearningStyle,
    Persona,
    Profile,
    Role,
    SkillLevel,
    TopicRead,
)

app = typer.Typer(help="Neocortex — AI-powered developer learning assistant")
console = Console()

LEVEL_PROGRESS: dict[SkillLevel, tuple[int, str]] = {
    SkillLevel.BEGINNER: (4, "level_beginner"),
    SkillLevel.PROFICIENT: (10, "level_proficient"),
    SkillLevel.ADVANCED: (15, "level_advanced"),
    SkillLevel.EXPERT: (18, "level_expert"),
}

BAR_TOTAL = 20


def _get_lang() -> Language:
    from neocortex.config import load_config

    cfg = load_config()
    return cfg.output_settings.language


def smart_output(data: dict, human_format_fn, json_flag: bool = False) -> None:
    if json_flag or not sys.stdout.isatty():
        typer.echo(json_lib.dumps(data, ensure_ascii=False, indent=2))
    else:
        human_format_fn(data)


def _mask_api_key(key: str | None) -> str:
    if not key:
        return "(not set)"
    if len(key) <= 8:
        return key
    return key[:8] + "..."


def _skill_bar(level: SkillLevel, lang: Language) -> Text:
    filled, label_key = LEVEL_PROGRESS[level]
    label = t(label_key, lang)
    bar_filled = "\u2588" * filled
    bar_empty = "\u2591" * (BAR_TOTAL - filled)
    text = Text()
    text.append(bar_filled, style="green")
    text.append(bar_empty, style="dim")
    text.append(f"  {label}", style="bold")
    return text


def calibrate(feedback: str, calibration: Calibration) -> Calibration:
    if feedback == "too_easy":
        calibration.consecutive_too_easy += 1
        calibration.consecutive_too_hard = 0
        if calibration.consecutive_too_easy >= 2:
            calibration.level_offset = min(calibration.level_offset + 1, 2)
            calibration.consecutive_too_easy = 0
    elif feedback == "too_hard":
        calibration.consecutive_too_hard += 1
        calibration.consecutive_too_easy = 0
        if calibration.consecutive_too_hard >= 2:
            calibration.level_offset = max(calibration.level_offset - 1, -2)
            calibration.consecutive_too_hard = 0
    else:
        calibration.consecutive_too_easy = 0
        calibration.consecutive_too_hard = 0
    return calibration


@app.command()
def init() -> None:
    """First-time setup: role, experience, goals, language."""
    from neocortex.config import load_config, load_profile, save_config, save_profile

    cfg = load_config()
    prof = load_profile()
    lang = cfg.output_settings.language

    console.print()
    console.print(f"  [bold]{t('init_welcome', lang)}[/bold]")
    console.print()

    role_choices = {
        t("role_backend", lang): Role.BACKEND,
        t("role_frontend", lang): Role.FRONTEND,
        t("role_fullstack", lang): Role.FULLSTACK,
        t("role_student", lang): Role.STUDENT,
        t("role_self_taught", lang): Role.SELF_TAUGHT,
    }
    role_labels = list(role_choices.keys())
    role_answer = Prompt.ask(
        f"  [bold]?[/bold] {t('init_role', lang)}",
        choices=role_labels,
        default=role_labels[0],
        console=console,
    )
    selected_role = role_choices[role_answer]

    exp_choices = {
        t("exp_0_1", lang): ExperienceRange.JUNIOR,
        t("exp_1_3", lang): ExperienceRange.MID,
        t("exp_3_5", lang): ExperienceRange.SENIOR,
        t("exp_5_plus", lang): ExperienceRange.EXPERT,
    }
    exp_labels = list(exp_choices.keys())
    exp_answer = Prompt.ask(
        f"  [bold]?[/bold] {t('init_experience', lang)}",
        choices=exp_labels,
        default=exp_labels[0],
        console=console,
    )
    selected_exp = exp_choices[exp_answer]

    goal_choices = {
        t("goal_system_design", lang): LearningGoal.SYSTEM_DESIGN,
        t("goal_new_framework", lang): LearningGoal.NEW_FRAMEWORK,
        t("goal_interview", lang): LearningGoal.INTERVIEW,
        t("goal_level_up", lang): LearningGoal.LEVEL_UP,
        t("goal_side_project", lang): LearningGoal.SIDE_PROJECT,
    }
    goal_labels = list(goal_choices.keys())
    goal_answer = Prompt.ask(
        f"  [bold]?[/bold] {t('init_goal', lang)}",
        choices=goal_labels,
        default=goal_labels[0],
        console=console,
    )
    selected_goal = goal_choices[goal_answer]

    style_choices = {
        t("style_code", lang): LearningStyle.CODE_EXAMPLES,
        t("style_theory", lang): LearningStyle.THEORY_FIRST,
        t("style_do_it", lang): LearningStyle.JUST_DO_IT,
        t("style_compare", lang): LearningStyle.COMPARE_WITH_KNOWN,
    }
    style_labels = list(style_choices.keys())
    style_answer = Prompt.ask(
        f"  [bold]?[/bold] {t('init_style', lang)}",
        choices=style_labels,
        default=style_labels[0],
        console=console,
    )
    selected_style = style_choices[style_answer]

    lang_choices = {
        t("lang_en", lang): Language.EN,
        t("lang_zh", lang): Language.ZH,
    }
    lang_labels = list(lang_choices.keys())
    lang_answer = Prompt.ask(
        f"  [bold]?[/bold] {t('init_language', lang)}",
        choices=lang_labels,
        default=lang_labels[0],
        console=console,
    )
    selected_lang = lang_choices[lang_answer]

    prof.persona = Persona(
        role=selected_role,
        experience_years=selected_exp,
        learning_goal=selected_goal,
        learning_style=selected_style,
        language=selected_lang,
    )
    save_profile(prof)

    cfg.output_settings.language = selected_lang
    save_config(cfg)

    console.print()
    console.print(f"  {t('init_done', selected_lang)}")
    console.print()


@app.command()
def config(
    provider: str = typer.Option(None, help="LLM provider"),
    api_key: str = typer.Option(None, help="API key"),
    base_url: str = typer.Option(None, help="Base URL for openai-compat"),
    model: str = typer.Option(None, help="Model name"),
    language: str = typer.Option(None, help="Note language (en/zh)"),
) -> None:
    """Configure LLM provider, API key, and preferences."""
    from neocortex.config import load_config, save_config
    from neocortex.models import ProviderType

    cfg = load_config()
    lang = cfg.output_settings.language

    has_updates = any(v is not None for v in [provider, api_key, base_url, model, language])

    if not has_updates:
        console.print()
        console.print(f"  [bold]{t('config_show', lang)}[/bold]")
        console.print()
        console.print(f"  provider:   {cfg.provider.value if cfg.provider else '(not set)'}")
        console.print(f"  api_key:    {_mask_api_key(cfg.api_key)}")
        console.print(f"  base_url:   {cfg.base_url or '(not set)'}")
        console.print(f"  model:      {cfg.model or '(not set)'}")
        console.print(f"  language:   {cfg.output_settings.language.value}")
        console.print()
        return

    if provider is not None:
        try:
            cfg.provider = ProviderType(provider)
        except ValueError:
            valid = ", ".join(p.value for p in ProviderType)
            console.print(f"  [red]{t('error', lang)}: Invalid provider '{provider}'. Valid: {valid}[/red]")
            raise typer.Exit(1)

    if api_key is not None:
        cfg.api_key = api_key

    if base_url is not None:
        cfg.base_url = base_url

    if model is not None:
        cfg.model = model

    if language is not None:
        try:
            cfg.output_settings.language = Language(language)
        except ValueError:
            console.print(f"  [red]{t('error', lang)}: Invalid language '{language}'. Valid: en, zh[/red]")
            raise typer.Exit(1)

    save_config(cfg)
    console.print(f"  {t('config_saved', cfg.output_settings.language)}")


@app.command()
def scan(
    paths: list[str] = typer.Argument(..., help="Project paths to scan"),
    update: bool = typer.Option(False, help="Update existing profile"),
) -> None:
    """Scan local projects to build/update your skill profile."""
    from neocortex.config import load_config, load_profile, save_profile
    from neocortex.llm import create_provider
    from neocortex.scanner.extractors import extract_key_files
    from neocortex.scanner.profile import merge_profiles
    from neocortex.scanner.project import ProjectScanner

    cfg = load_config()
    lang = cfg.output_settings.language
    prof = load_profile()

    if not paths:
        console.print(f"  [red]{t('scan_no_projects', lang)}[/red]")
        raise typer.Exit(1)

    try:
        provider = create_provider(cfg)
    except ValueError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
        raise typer.Exit(1)

    scanner = ProjectScanner(cfg.scan_settings.exclude_patterns)

    async def _run_scan() -> None:
        from neocortex.scanner.analyzer import analyze_project

        all_skills = prof.skills if update else None

        for p in paths:
            resolved = Path(p).resolve()
            if not resolved.is_dir():
                console.print(f"  [red]{t('scan_not_found', lang, path=str(resolved))}[/red]")
                continue

            with console.status(f"  {t('scan_project', lang, name=resolved.name)}"):
                project_info = scanner.scan(str(resolved))

            langs_str = ", ".join(
                f"{ln} ({lines})"
                for ln, lines in sorted(project_info.languages.items(), key=lambda x: -x[1])
            )
            frameworks_str = ", ".join(project_info.frameworks) if project_info.frameworks else "-"
            console.print(f"  {t('scan_detected', lang, langs=langs_str or '-', frameworks=frameworks_str)}")

            with console.status(f"  {t('analyzing', lang)}"):
                key_files = extract_key_files(
                    str(resolved),
                    max_lines=cfg.scan_settings.max_file_lines,
                    exclude_patterns=cfg.scan_settings.exclude_patterns,
                )
                skills = await analyze_project(project_info, key_files, provider)

            if all_skills is not None:
                all_skills = merge_profiles(all_skills, skills)
            else:
                all_skills = skills

        if all_skills is not None:
            prof.skills = all_skills
            save_profile(prof)
            console.print(f"  [green]{t('scan_complete', lang)}[/green]")

    asyncio.run(_run_scan())


@app.command()
def profile(
    export: str = typer.Option(None, help="Export profile to file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    edit: bool = typer.Option(False, "--edit", help="Open profile in editor"),
) -> None:
    """View, export, or edit your skill profile."""
    from neocortex.config import load_profile, get_data_dir

    if edit:
        import os
        import subprocess
        profile_path = get_data_dir() / "profile.json"
        editor = os.environ.get("EDITOR", "vi")
        subprocess.run([editor, str(profile_path)])
        return

    prof = load_profile()
    lang = _get_lang()
    data = prof.model_dump(mode="json")

    if export is not None:
        export_path = Path(export)
        export_path.write_text(
            json_lib.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        console.print(f"  {t('profile_exported', lang, path=str(export_path))}")
        return

    def _human_format(d: dict) -> None:
        skills = prof.skills

        has_any = (
            skills.languages
            or skills.domains
            or skills.integrations
            or skills.architecture
        )
        if not has_any:
            console.print(f"  {t('profile_empty', lang)}")
            return

        console.print()
        console.print(f"  [bold]{t('profile_title', lang)}[/bold]")
        console.print("  " + "\u2501" * 52)

        if skills.languages:
            console.print()
            console.print(f"  [bold]{t('profile_languages', lang)}[/bold]")
            for name, skill in skills.languages.items():
                lines_display = _format_lines(skill.lines)
                projects_display = f"{len(skill.projects)} project{'s' if len(skill.projects) != 1 else ''}"
                bar = _skill_bar(skill.level, lang)
                line = Text()
                line.append(f"  {name:<16}", style="cyan")
                line.append_text(bar)
                line.append(f"  ({lines_display}, {projects_display})")
                console.print(line)
                if skill.frameworks:
                    console.print(f"                    {t('profile_frameworks', lang)}: {', '.join(skill.frameworks)}")

        if skills.domains:
            console.print()
            console.print(f"  [bold]{t('profile_domains', lang)}[/bold]")
            for name, skill in skills.domains.items():
                bar = _skill_bar(skill.level, lang)
                line = Text()
                line.append(f"  {name:<16}", style="cyan")
                line.append_text(bar)
                console.print(line)
                if skill.gaps:
                    for gap in skill.gaps:
                        console.print(f"                    [dim]gap: {gap}[/dim]")

        if skills.integrations:
            console.print()
            console.print(f"  [bold]{t('profile_integrations', lang)}[/bold]")
            for name, skill in skills.integrations.items():
                bar = _skill_bar(skill.level, lang)
                line = Text()
                line.append(f"  {name:<16}", style="cyan")
                line.append_text(bar)
                console.print(line)

        if skills.architecture:
            console.print()
            console.print(f"  [bold]{t('profile_architecture', lang)}[/bold]")
            for name, skill in skills.architecture.items():
                bar = _skill_bar(skill.level, lang)
                line = Text()
                line.append(f"  {name:<16}", style="cyan")
                line.append_text(bar)
                console.print(line)

        console.print()

    smart_output(data, _human_format, json_output)


@app.command()
def read(
    source: str = typer.Argument(..., help="URL, PDF, or file path"),
    focus: str = typer.Option(None, help="Focus topic"),
    question: str = typer.Option(None, help="Question to answer"),
) -> None:
    """Read a URL/file and generate personalized notes."""
    from neocortex.config import get_notes_dir, load_config, load_profile, save_profile
    from neocortex.llm import create_provider

    cfg = load_config()
    lang = cfg.output_settings.language
    prof = load_profile()

    try:
        provider = create_provider(cfg)
    except ValueError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
        raise typer.Exit(1)

    async def _run_read() -> None:
        from neocortex.reader.fetcher import ContentFetcher
        from neocortex.reader.teacher import generate_notes, generate_outline

        fetcher = ContentFetcher()

        with console.status(f"  {t('read_fetching', lang)}"):
            doc = await fetcher.fetch(source)

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
            choices=["Y", "n"],
            default="Y",
            console=console,
        )
        if confirm.lower() == "n":
            return

        with console.status(f"  {t('read_generating', lang)}"):
            notes_content = await generate_notes(
                doc, outline, prof, provider,
                focus=focus,
                question=question,
            )

        notes_dir = get_notes_dir()
        safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in doc.title)
        safe_title = safe_title.strip().replace(" ", "-").lower()[:60]
        if not safe_title:
            safe_title = "note"
        today = date.today().isoformat()
        filename = f"{safe_title}-{today}.md"
        note_path = notes_dir / filename
        note_path.write_text(notes_content, encoding="utf-8")

        console.print()
        console.print(f"  [green]{t('read_saved', lang, path=str(note_path))}[/green]")

        if cfg.output_settings.auto_open:
            import platform
            import subprocess
            opener = "open" if platform.system() == "Darwin" else "xdg-open"
            try:
                subprocess.Popen([opener, str(note_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass

        _collect_feedback(lang, prof, source, doc.title, focus, note_path)

    asyncio.run(_run_read())


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


@app.command("import")
def import_data(
    path: str = typer.Argument(None, help="Path to export file/directory"),
    source: str = typer.Option(None, help="Source: chatgpt or claude"),
    clear: bool = typer.Option(False, help="Clear imported insights"),
) -> None:
    """Import chat history (chatgpt/claude) to enrich your profile."""
    from neocortex.config import load_config, load_profile, save_profile
    from neocortex.llm import create_provider

    cfg = load_config()
    lang = cfg.output_settings.language
    prof = load_profile()

    if clear:
        prof.chat_insights = None
        save_profile(prof)
        console.print(f"  {t('import_cleared', lang)}")
        return

    if not source:
        console.print("[red]--source is required (chatgpt or claude)[/red]")
        raise typer.Exit(1)
    if not path:
        console.print("[red]Path to export file is required[/red]")
        raise typer.Exit(1)

    resolved_path = Path(path).resolve()
    if not resolved_path.exists():
        console.print(f"  [red]{t('error', lang)}: Path not found: {resolved_path}[/red]")
        raise typer.Exit(1)

    valid_sources = ("chatgpt", "claude")
    if source not in valid_sources:
        console.print(f"  [red]{t('error', lang)}: Invalid source '{source}'. Valid: {', '.join(valid_sources)}[/red]")
        raise typer.Exit(1)

    try:
        provider = create_provider(cfg)
    except ValueError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
        raise typer.Exit(1)

    async def _run_import() -> None:
        from neocortex.importer.extractor import extract_insights
        from neocortex.importer.merger import cross_validate, merge_insights_to_profile

        with console.status(f"  {t('import_parsing', lang, source=source)}"):
            if source == "chatgpt":
                from neocortex.importer.chatgpt import parse_chatgpt_export
                messages = parse_chatgpt_export(str(resolved_path))
            else:
                from neocortex.importer.claude import parse_claude_export
                messages = parse_claude_export(str(resolved_path))

        if not messages:
            console.print(f"  [yellow]{t('import_no_messages', lang)}[/yellow]")
            return

        with console.status(f"  {t('import_extracting', lang, count=str(len(messages)))}"):
            insights = await extract_insights(messages, provider, source)

        merge_insights_to_profile(prof, insights)
        cross_validate(prof.skills, insights)
        save_profile(prof)

        console.print(f"  [green]{t('import_done', lang)}[/green]")

    asyncio.run(_run_import())


@app.command()
def notes(
    search: str = typer.Option(None, help="Search notes"),
) -> None:
    """List or search your knowledge base."""
    from neocortex.config import get_notes_dir

    lang = _get_lang()
    notes_dir = get_notes_dir()

    md_files = sorted(notes_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)

    if not md_files:
        console.print(f"  {t('notes_empty', lang)}")
        return

    if search:
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


def _format_lines(lines: int) -> str:
    if lines >= 1000:
        return f"{lines // 1000}K+ lines"
    return f"{lines} lines"
