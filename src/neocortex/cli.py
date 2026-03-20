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


def _numbered_select(question: str, options: list[tuple[str, any]], default: int = 1) -> any:
    """Show numbered options. Accept number, label substring, or fuzzy match."""
    console.print(f"  [bold]?[/bold] {question}")
    for i, (label, _) in enumerate(options, 1):
        marker = "[bold cyan]>[/bold cyan]" if i == default else " "
        console.print(f"  {marker} [cyan]{i}[/cyan]) {label}")

    while True:
        raw = Prompt.ask(f"    [dim]({default})[/dim]", default=str(default), console=console).strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1][1]
        lower = raw.lower()
        for i, (label, value) in enumerate(options):
            if lower == label.lower() or lower in label.lower():
                return value
        console.print(f"    [dim]输入数字 1-{len(options)} 或关键词[/dim]")


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

    # ── Step 1: Language first (affects all subsequent prompts) ──
    console.print()
    console.print("  [bold]Welcome to Neocortex / 欢迎使用 Neocortex[/bold]")
    console.print()

    selected_lang = _numbered_select("Language / 语言", [
        ("English", Language.EN),
        ("中文", Language.ZH),
    ])
    lang = selected_lang

    # ── Step 2: Quick intro ──
    console.print()
    console.print(f"  [bold]{t('init_welcome', lang)}[/bold]")
    console.print()

    selected_role = _numbered_select(t("init_role", lang), [
        (t("role_backend", lang), Role.BACKEND),
        (t("role_frontend", lang), Role.FRONTEND),
        (t("role_fullstack", lang), Role.FULLSTACK),
        (t("role_student", lang), Role.STUDENT),
        (t("role_self_taught", lang), Role.SELF_TAUGHT),
    ])

    selected_exp = _numbered_select(t("init_experience", lang), [
        (t("exp_0_1", lang), ExperienceRange.JUNIOR),
        (t("exp_1_3", lang), ExperienceRange.MID),
        (t("exp_3_5", lang), ExperienceRange.SENIOR),
        (t("exp_5_plus", lang), ExperienceRange.EXPERT),
    ])

    selected_goal = _numbered_select(t("init_goal", lang), [
        (t("goal_system_design", lang), LearningGoal.SYSTEM_DESIGN),
        (t("goal_new_framework", lang), LearningGoal.NEW_FRAMEWORK),
        (t("goal_interview", lang), LearningGoal.INTERVIEW),
        (t("goal_level_up", lang), LearningGoal.LEVEL_UP),
        (t("goal_side_project", lang), LearningGoal.SIDE_PROJECT),
    ])

    selected_style = _numbered_select(t("init_style", lang), [
        (t("style_code", lang), LearningStyle.CODE_EXAMPLES),
        (t("style_theory", lang), LearningStyle.THEORY_FIRST),
        (t("style_do_it", lang), LearningStyle.JUST_DO_IT),
        (t("style_compare", lang), LearningStyle.COMPARE_WITH_KNOWN),
    ])

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

    # ── Step 3: Auto-discover and scan projects ──
    console.print()

    if not cfg.provider:
        console.print(f"  [yellow]{t('config_no_provider', lang)}[/yellow]")
        console.print(f"  {t('init_done', lang)}")
        console.print()
        return

    from neocortex.discovery import discover_projects

    console.print(f"  [bold]{t('init_scanning_title', lang)}[/bold]")
    with console.status(f"  {t('init_discovering', lang)}"):
        projects = discover_projects()

    if not projects:
        console.print(f"  [dim]{t('init_no_projects', lang)}[/dim]")
        console.print()
        console.print(f"  {t('init_done', lang)}")
        console.print()
        return

    console.print(f"  {t('init_found_projects', lang, count=str(len(projects)))}")
    console.print()
    for i, p in enumerate(projects[:15], 1):
        console.print(f"    {i:2d}. [cyan]{p['name']}[/cyan] [dim]({p['type']})[/dim] {p['path']}")
    if len(projects) > 15:
        console.print(f"    ... {t('init_more_projects', lang, count=str(len(projects) - 15))}")
    console.print()

    scan_answer = Prompt.ask(
        f"  [bold]?[/bold] {t('init_scan_confirm', lang)}",
        choices=["Y", "n"],
        default="Y",
        console=console,
    )

    if scan_answer.lower() == "n":
        console.print()
        console.print(f"  {t('init_done', lang)}")
        console.print()
        return

    # Scan selected projects
    from neocortex.config import get_data_dir, get_notes_dir
    from neocortex.llm import create_provider
    from neocortex.scanner.extractors import extract_key_files
    from neocortex.scanner.profile import merge_profiles
    from neocortex.scanner.project import ProjectScanner

    try:
        provider = create_provider(cfg)
    except ValueError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
        console.print(f"  {t('init_done', lang)}")
        console.print()
        return

    scanner = ProjectScanner(cfg.scan_settings.exclude_patterns)
    scan_paths = [p["path"] for p in projects[:10]]

    async def _run_init_scan() -> None:
        from neocortex.scanner.analyzer import analyze_project

        all_skills = None
        for p_path in scan_paths:
            name = Path(p_path).name
            with console.status(f"  {t('scan_project', lang, name=name)}"):
                project_info = scanner.scan(p_path)
                key_files = extract_key_files(
                    p_path,
                    max_lines=cfg.scan_settings.max_file_lines,
                    exclude_patterns=cfg.scan_settings.exclude_patterns,
                )
                skills = await analyze_project(project_info, key_files, provider)

            langs_str = ", ".join(
                f"{ln} ({lines})" for ln, lines in sorted(project_info.languages.items(), key=lambda x: -x[1])
            ) or "-"
            console.print(f"  [dim]  {name}: {langs_str}[/dim]")

            if all_skills is not None:
                all_skills = merge_profiles(all_skills, skills)
            else:
                all_skills = skills

        if all_skills is not None:
            prof.skills = all_skills
            save_profile(prof)
            from neocortex.growth import save_snapshot
            notes_count = len(list(get_notes_dir().glob("*.md")))
            save_snapshot(prof, get_data_dir(), notes_count)

    asyncio.run(_run_init_scan())

    # ── Step 4: Show result + next steps ──
    console.print()
    console.print(f"  [bold green]{t('init_complete', lang)}[/bold green]")
    console.print()

    # Show top skills
    top_langs = sorted(prof.skills.languages.items(), key=lambda x: -x[1].lines)[:5]
    if top_langs:
        console.print(f"  [bold]{t('profile_languages', lang)}[/bold]")
        for name, skill in top_langs:
            bar = _skill_bar(skill.level, lang)
            line = Text()
            line.append(f"    {name:<14}", style="cyan")
            line.append_text(bar)
            if skill.lines > 0:
                line.append(f"  ({_format_lines(skill.lines)})", style="dim")
            console.print(line)
        console.print()

    # Next steps
    console.print(f"  [bold]{t('init_next_steps', lang)}[/bold]")
    console.print(f"    neocortex read <url>              {t('init_hint_read', lang)}")
    console.print(f"    neocortex ask \"your question\"     {t('init_hint_ask', lang)}")
    console.print(f"    neocortex recommend               {t('init_hint_recommend', lang)}")
    console.print(f"    neocortex profile                 {t('init_hint_profile', lang)}")
    console.print()


@app.command()
def config(
    provider: str = typer.Option(None, help="LLM provider"),
    api_key: str = typer.Option(None, help="API key"),
    base_url: str = typer.Option(None, help="Base URL for openai-compat"),
    model: str = typer.Option(None, help="Model name"),
    language: str = typer.Option(None, help="Note language (en/zh)"),
    github_token: str = typer.Option(None, "--github-token", help="GitHub Personal Access Token"),
) -> None:
    """Configure LLM provider, API key, and preferences."""
    from neocortex.config import load_config, save_config
    from neocortex.models import ProviderType

    cfg = load_config()
    lang = cfg.output_settings.language

    has_updates = any(v is not None for v in [provider, api_key, base_url, model, language, github_token])

    if not has_updates:
        console.print()
        console.print(f"  [bold]{t('config_show', lang)}[/bold]")
        console.print()
        console.print(f"  provider:      {cfg.provider.value if cfg.provider else '(not set)'}")
        console.print(f"  api_key:       {_mask_api_key(cfg.api_key)}")
        console.print(f"  base_url:      {cfg.base_url or '(not set)'}")
        console.print(f"  model:         {cfg.model or '(not set)'}")
        console.print(f"  github_token:  {_mask_api_key(cfg.github_token)}")
        console.print(f"  language:      {cfg.output_settings.language.value}")
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

    if github_token is not None:
        cfg.github_token = github_token

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
    paths: list[str] = typer.Argument(None, help="Local project paths to scan"),
    github: str = typer.Option(None, "--github", help="GitHub username or user/repo to scan"),
    update: bool = typer.Option(False, help="Update existing profile"),
) -> None:
    """Scan local projects or GitHub repos to build/update your skill profile."""
    import subprocess

    import httpx

    from neocortex.config import load_config, load_profile, save_profile, get_data_dir, get_notes_dir
    from neocortex.llm import create_provider
    from neocortex.models import Skills
    from neocortex.scanner.extractors import extract_key_files
    from neocortex.scanner.profile import merge_profiles
    from neocortex.scanner.project import ProjectScanner

    cfg = load_config()
    lang = cfg.output_settings.language
    prof = load_profile()

    if not paths and not github:
        console.print(f"  [red]{t('scan_no_projects', lang)}[/red]")
        raise typer.Exit(1)

    try:
        provider = create_provider(cfg)
    except ValueError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
        raise typer.Exit(1)

    scanner = ProjectScanner(cfg.scan_settings.exclude_patterns)

    async def _scan_local_paths(all_skills: Skills | None) -> Skills | None:
        from neocortex.scanner.analyzer import analyze_project

        if not paths:
            return all_skills

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

        return all_skills

    async def _scan_github(all_skills: Skills | None) -> Skills | None:
        from neocortex.scanner.analyzer import analyze_project
        from neocortex.scanner.github import (
            cleanup_repo,
            clone_repo,
            get_single_repo,
            list_user_repos,
        )

        if not github:
            return all_skills

        token = cfg.github_token

        if "/" in github:
            owner, repo_name = github.split("/", 1)
            try:
                with console.status(f"  {t('github_listing', lang, user=github)}"):
                    repo_info = await get_single_repo(owner, repo_name, token)
                repos = [repo_info]
            except httpx.HTTPStatusError as exc:
                console.print(f"  [red]{t('github_api_error', lang, error=str(exc.response.status_code))}[/red]")
                return all_skills
        else:
            try:
                with console.status(f"  {t('github_listing', lang, user=github)}"):
                    repos = await list_user_repos(github, token)
            except httpx.HTTPStatusError as exc:
                console.print(f"  [red]{t('github_api_error', lang, error=str(exc.response.status_code))}[/red]")
                return all_skills

            if not repos:
                console.print(f"  [yellow]{t('github_no_repos', lang, user=github)}[/yellow]")
                return all_skills

            repos = repos[:10]

        console.print(f"  {t('github_scanning', lang, count=str(len(repos)))}")

        for repo in repos:
            clone_path = None
            try:
                with console.status(f"  {t('github_cloning', lang, repo=repo['full_name'])}"):
                    clone_path = await clone_repo(repo["clone_url"], token)

                with console.status(f"  {t('scan_project', lang, name=repo['name'])}"):
                    project_info = scanner.scan(str(clone_path))

                langs_str = ", ".join(
                    f"{ln} ({lines})"
                    for ln, lines in sorted(project_info.languages.items(), key=lambda x: -x[1])
                )
                frameworks_str = ", ".join(project_info.frameworks) if project_info.frameworks else "-"
                console.print(f"  {t('scan_detected', lang, langs=langs_str or '-', frameworks=frameworks_str)}")

                with console.status(f"  {t('analyzing', lang)}"):
                    key_files = extract_key_files(
                        str(clone_path),
                        max_lines=cfg.scan_settings.max_file_lines,
                        exclude_patterns=cfg.scan_settings.exclude_patterns,
                    )
                    skills = await analyze_project(project_info, key_files, provider)

                if all_skills is not None:
                    all_skills = merge_profiles(all_skills, skills)
                else:
                    all_skills = skills

            except subprocess.CalledProcessError:
                console.print(f"  [red]{t('github_clone_failed', lang, repo=repo['full_name'], error='clone failed')}[/red]")
            finally:
                if clone_path is not None:
                    cleanup_repo(clone_path)

        return all_skills

    async def _run_scan() -> None:
        all_skills = prof.skills if update else None

        all_skills = await _scan_local_paths(all_skills)
        all_skills = await _scan_github(all_skills)

        if all_skills is not None:
            prof.skills = all_skills
            save_profile(prof)

            from neocortex.growth import save_snapshot
            notes_count = len(list(get_notes_dir().glob("*.md")))
            save_snapshot(prof, get_data_dir(), notes_count)

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
    audio: bool = typer.Option(False, "--audio", help="Generate audio version"),
) -> None:
    """Read a URL/file and generate personalized notes."""
    from neocortex.config import get_data_dir, get_notes_dir, load_config, load_profile, save_profile
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
        counter = 1
        while note_path.exists():
            counter += 1
            filename = f"{safe_title}-{today}-{counter}.md"
            note_path = notes_dir / filename
        note_path.write_text(notes_content, encoding="utf-8")

        from neocortex.search import NoteIndex

        note_index = NoteIndex(get_data_dir() / "neocortex.sqlite")
        note_index.index_note(note_path.name, doc.title, notes_content)

        console.print()
        console.print(f"  [green]{t('read_saved', lang, path=str(note_path))}[/green]")

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
def recommend(
    count: int = typer.Option(5, help="Number of recommendations"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Get personalized learning recommendations based on your profile."""
    from neocortex.config import load_config, load_profile
    from neocortex.llm import create_provider
    from neocortex.recommender import generate_recommendations

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

    async def _run() -> list:
        with console.status(f"  {t('recommend_generating', lang)}"):
            return await generate_recommendations(prof, provider, count, lang)

    recs = asyncio.run(_run())

    if not recs:
        console.print(f"  [yellow]{t('recommend_empty', lang)}[/yellow]")
        return

    if json_output or not sys.stdout.isatty():
        typer.echo(json_lib.dumps(
            [r.model_dump(mode="json") for r in recs],
            ensure_ascii=False, indent=2,
        ))
        return

    console.print()
    console.print(f"  [bold]{t('recommend_title', lang)}[/bold]")
    console.print("  " + "\u2501" * 52)

    priority_icons = {"high": "[red]!!![/red]", "medium": "[yellow]!![/yellow]", "low": "[dim]![/dim]"}

    for i, rec in enumerate(recs, 1):
        icon = priority_icons.get(rec.priority, "[yellow]!![/yellow]")
        console.print()
        console.print(f"  {icon} [bold cyan]{i}. {rec.topic}[/bold cyan]")
        console.print(f"     {rec.reason}")
        if rec.expected_benefit:
            console.print(f"     [green]{t('recommend_benefit', lang)}[/green] {rec.expected_benefit}")
        if rec.resources:
            console.print(f"     [dim]{t('recommend_resources', lang)}[/dim]")
            for res in rec.resources:
                console.print(f"       - {res}")

    console.print()


@app.command()
def plan(
    weeks: int = typer.Option(4, help="Number of weeks"),
) -> None:
    """Generate a personalized learning plan."""
    from neocortex.config import get_data_dir, get_notes_dir, load_config, load_profile
    from neocortex.llm import create_provider
    from neocortex.planner import generate_plan

    cfg = load_config()
    prof = load_profile()
    lang = cfg.output_settings.language

    if not prof.skills.languages and not prof.skills.domains:
        console.print(f"  {t('profile_empty', lang)}")
        raise typer.Exit(1)

    try:
        provider = create_provider(cfg)
    except ValueError as exc:
        console.print(f"  [red]{t('error', lang)}: {exc}[/red]")
        raise typer.Exit(1)

    async def _run() -> str:
        with console.status(f"  {t('plan_generating', lang)}"):
            return await generate_plan(prof, provider, weeks, lang)

    plan_md = asyncio.run(_run())

    today = date.today().isoformat()
    plan_md = plan_md.replace("{date}", today)

    notes_dir = get_notes_dir()
    filename = f"learning-plan-{today}.md"
    plan_path = notes_dir / filename
    counter = 1
    while plan_path.exists():
        counter += 1
        filename = f"learning-plan-{today}-{counter}.md"
        plan_path = notes_dir / filename
    plan_path.write_text(plan_md, encoding="utf-8")

    from neocortex.search import NoteIndex

    note_index = NoteIndex(get_data_dir() / "neocortex.sqlite")
    title = "Personalized Learning Plan" if lang == Language.EN else "个性化学习计划"
    note_index.index_note(plan_path.name, title, plan_md)

    console.print()
    console.print(f"  [green]{t('plan_saved', lang, path=str(plan_path))}[/green]")
    console.print()

    if cfg.output_settings.auto_open:
        import platform
        import subprocess
        opener = "open" if platform.system() == "Darwin" else "xdg-open"
        try:
            subprocess.Popen([opener, str(plan_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


@app.command()
def growth(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show your skill growth over time."""
    from neocortex.config import get_data_dir
    from neocortex.growth import load_snapshots, compute_diff

    lang = _get_lang()
    snapshots = load_snapshots(get_data_dir())

    if len(snapshots) < 1:
        console.print(f"  [yellow]{t('growth_no_data', lang)}[/yellow]")
        return

    if json_output or not sys.stdout.isatty():
        if len(snapshots) >= 2:
            diff = compute_diff(snapshots[0], snapshots[-1])
            typer.echo(json_lib.dumps(diff, ensure_ascii=False, indent=2))
        else:
            typer.echo(json_lib.dumps({"snapshots": 1, "message": "Need at least 2 scans to show growth"}, ensure_ascii=False, indent=2))
        return

    console.print()
    console.print(f"  [bold]{t('growth_title', lang)}[/bold]")
    console.print("  " + "\u2501" * 52)

    latest = snapshots[-1]
    console.print(f"\n  [dim]{t('growth_snapshots', lang, count=str(len(snapshots)))}[/dim]")
    console.print(f"  {t('growth_current', lang)}  [bold]{latest.total_lines:,}[/bold] lines | [bold]{latest.total_projects}[/bold] projects | [bold]{latest.notes_count}[/bold] notes")

    if len(snapshots) >= 2:
        diff = compute_diff(snapshots[0], snapshots[-1])
        console.print(f"\n  [bold]{diff['period']}[/bold]")

        if diff["lines_delta"] > 0:
            console.print(f"  [green]+{diff['lines_delta']:,} lines[/green]")
        if diff["projects_delta"] > 0:
            console.print(f"  [green]+{diff['projects_delta']} projects[/green]")
        if diff["notes_delta"] > 0:
            console.print(f"  [green]+{diff['notes_delta']} notes[/green]")

        if diff["new_languages"]:
            console.print(f"\n  [bold cyan]{t('growth_new_langs', lang)}[/bold cyan]")
            for lang_name in diff["new_languages"]:
                console.print(f"    + {lang_name}")

        if diff["level_ups"]:
            console.print(f"\n  [bold green]{t('growth_level_ups', lang)}[/bold green]")
            for up in diff["level_ups"]:
                console.print(f"    {up['skill']}: {up['from']} → {up['to']}")

        if diff["new_domains"]:
            console.print(f"\n  [bold cyan]{t('growth_new_domains', lang)}[/bold cyan]")
            for d in diff["new_domains"]:
                console.print(f"    + {d}")

        if diff["gaps_closed"]:
            console.print(f"\n  [bold green]{t('growth_gaps_closed', lang)}[/bold green]")
            for g in diff["gaps_closed"]:
                console.print(f"    ✓ {g}")

    console.print()


@app.command()
def ask(
    question: str = typer.Argument(..., help="Your question"),
) -> None:
    """Ask a question with your skill profile as context."""
    from neocortex.config import load_config, load_profile
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
def notes(
    search: str = typer.Option(None, help="Search notes"),
) -> None:
    """List or search your knowledge base."""
    from neocortex.config import get_data_dir, get_notes_dir

    lang = _get_lang()
    notes_dir = get_notes_dir()

    md_files = sorted(notes_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)

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


def _format_lines(lines: int) -> str:
    if lines >= 1000:
        return f"{lines // 1000}K+ lines"
    return f"{lines} lines"
