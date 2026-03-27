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


def _maybe_migrate_notes() -> None:
    """Check for notes in old location (~/.neocortex/notes/) and offer to migrate."""
    from neocortex.config import get_data_dir, get_notes_dir

    old_dir = get_data_dir() / "notes"
    new_dir = get_notes_dir()

    if not old_dir.exists() or old_dir == new_dir:
        return

    old_notes = list(old_dir.glob("*.md"))
    if not old_notes:
        return

    lang = _get_lang()
    console.print()
    console.print(f"  [yellow]{t('notes_migrate_found', lang, count=str(len(old_notes)), old=str(old_dir), new=str(new_dir))}[/yellow]")

    answer = Prompt.ask(
        f"  [bold]?[/bold] {t('notes_migrate_confirm', lang)}",
        choices=["y", "n", "Y", "N"],
        default="y",
        console=console,
    )
    if answer.lower() != "y":
        return

    import shutil
    moved = 0
    for f in old_notes:
        dest = new_dir / f.name
        if not dest.exists():
            shutil.move(str(f), str(dest))
            moved += 1

    console.print(f"  [green]{t('notes_migrate_done', lang, count=str(moved))}[/green]")


def _arrow_select(
    question: str,
    options: list[tuple[str, any]],
    default: int = 0,
) -> any:
    """Arrow-key menu. Falls back to numbered input if terminal doesn't support it."""
    try:
        from InquirerPy import inquirer
        choices = [{"name": label, "value": value} for label, value in options]
        result = inquirer.select(
            message=question,
            choices=choices,
            default=choices[default]["value"],
            pointer=">",
            show_cursor=False,
        ).execute()
        return result
    except (ImportError, Exception):
        # Fallback: simple numbered input
        console.print(f"  [bold]?[/bold] {question}")
        for i, (label, _) in enumerate(options, 1):
            console.print(f"    [cyan]{i}[/cyan]) {label}")
        while True:
            raw = Prompt.ask(f"    [dim]({default + 1})[/dim]", default=str(default + 1), console=console).strip()
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return options[int(raw) - 1][1]
            lower = raw.lower()
            for label, value in options:
                if lower in label.lower():
                    return value
            console.print(f"    [dim]输入 1-{len(options)}[/dim]")


def _resolve_project_dir(raw: str) -> Path:
    """Smartly resolve a user-typed project directory path.

    Handles: absolute paths, ~, relative names, abbreviations, typos.
    """
    from difflib import get_close_matches

    p = Path(raw).expanduser()
    if p.is_absolute() and p.exists():
        return p.resolve()

    # Search common parent dirs for exact or fuzzy match
    search_parents = [
        Path.home() / "Documents",
        Path.home() / "Projects",
        Path.home() / "projects",
        Path.home() / "repos",
        Path.home() / "code",
        Path.home() / "dev",
        Path.home() / "work",
        Path.home() / "Work",
        Path.home(),
    ]

    query = raw.lower().strip().rstrip("/")

    for parent in search_parents:
        if not parent.exists():
            continue
        # Exact match
        candidate = parent / raw
        if candidate.exists():
            return candidate.resolve()
        # Case-insensitive + substring match
        try:
            subdirs = [d.name for d in parent.iterdir() if d.is_dir() and not d.name.startswith(".")]
        except PermissionError:
            continue
        for name in subdirs:
            if query == name.lower() or query in name.lower() or name.lower() in query:
                return (parent / name).resolve()
        # Prefix match (abbreviations: "bb" → "bitbucket")
        for name in subdirs:
            if name.lower().startswith(query):
                return (parent / name).resolve()
        # Fuzzy match (handles typos: "bitbukcet" → "bitbucket")
        matches = get_close_matches(query, [n.lower() for n in subdirs], n=1, cutoff=0.5)
        if matches:
            for name in subdirs:
                if name.lower() == matches[0]:
                    return (parent / name).resolve()

    # Last resort: treat as-is
    return p.resolve()


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


_DISPLAY_NAMES: dict[str, str] = {
    "aws": "AWS", "gcp": "GCP", "api": "API", "sdk": "SDK",
    "spa": "SPA", "ui": "UI", "sql": "SQL", "css": "CSS",
    "html": "HTML", "http": "HTTP", "rest": "REST", "graphql": "GraphQL",
    "oauth": "OAuth", "jwt": "JWT", "cdn": "CDN", "dns": "DNS",
    "ci": "CI", "cd": "CD", "orm": "ORM", "mvc": "MVC",
    "redis": "Redis", "mysql": "MySQL", "postgresql": "PostgreSQL",
    "mongodb": "MongoDB", "socketio": "Socket.IO", "websocket": "WebSocket",
    "openai": "OpenAI", "anthropic": "Anthropic", "aws_s3": "AWS S3",
    "dingtalk": "DingTalk", "paypal": "PayPal", "stripe": "Stripe",
    "celery": "Celery", "sqlalchemy": "SQLAlchemy", "fastapi": "FastAPI",
    "google_gemini": "Google Gemini", "google_api": "Google API",
    "twitter_api": "Twitter API",
}


def _format_display_name(key: str) -> str:
    """Convert snake_case key to human-readable display name."""
    if key in _DISPLAY_NAMES:
        return _DISPLAY_NAMES[key]
    words = key.replace("-", "_").split("_")
    parts = [_DISPLAY_NAMES.get(w, w.capitalize()) for w in words]
    return " ".join(parts)


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


def _format_lines(lines: int) -> str:
    if lines >= 1000:
        return f"{lines // 1000}K+ lines"
    return f"{lines} lines"


def _open_file(path: Path, lang: Language) -> None:
    """Open a file with the system default application."""
    import platform
    import subprocess
    opener = "open" if platform.system() == "Darwin" else "xdg-open"
    try:
        subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        console.print(f"  [green]{t('notes_opened', lang, path=path.name)}[/green]")
    except OSError:
        console.print(f"  [dim]{str(path)}[/dim]")


@app.command()
def init() -> None:
    """First-time setup: role, experience, goals, language."""
    from neocortex.config import load_config, load_profile, save_config, save_profile

    cfg = load_config()
    prof = load_profile()
    lang = cfg.output_settings.language

    # ── Step 1: Language ──
    console.print()
    console.print("  [bold]Welcome to Neocortex / 欢迎使用 Neocortex[/bold]")
    console.print()

    selected_lang = _arrow_select("Language / 语言", [
        ("English", Language.EN),
        ("中文", Language.ZH),
    ])
    lang = selected_lang

    # ── Step 2: Quick questionnaire (arrow-key select) ──
    console.print()
    console.print(f"  [bold]{t('init_welcome', lang)}[/bold]")
    console.print()

    selected_role = _arrow_select(t("init_role", lang), [
        (t("role_backend", lang), Role.BACKEND),
        (t("role_frontend", lang), Role.FRONTEND),
        (t("role_fullstack", lang), Role.FULLSTACK),
        (t("role_student", lang), Role.STUDENT),
        (t("role_self_taught", lang), Role.SELF_TAUGHT),
    ])

    selected_exp = _arrow_select(t("init_experience", lang), [
        (t("exp_0_1", lang), ExperienceRange.JUNIOR),
        (t("exp_1_3", lang), ExperienceRange.MID),
        (t("exp_3_5", lang), ExperienceRange.SENIOR),
        (t("exp_5_plus", lang), ExperienceRange.EXPERT),
    ])

    selected_goal = _arrow_select(t("init_goal", lang), [
        (t("goal_system_design", lang), LearningGoal.SYSTEM_DESIGN),
        (t("goal_new_framework", lang), LearningGoal.NEW_FRAMEWORK),
        (t("goal_interview", lang), LearningGoal.INTERVIEW),
        (t("goal_level_up", lang), LearningGoal.LEVEL_UP),
        (t("goal_side_project", lang), LearningGoal.SIDE_PROJECT),
    ])

    selected_style = _arrow_select(t("init_style", lang), [
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

    # ── Step 3: Project scanning ──
    console.print()

    if not cfg.provider:
        console.print(f"  [yellow]{t('config_no_provider', lang)}[/yellow]")
        console.print(f"  {t('init_done', lang)}")
        console.print()
        return

    from neocortex.discovery import discover_projects

    # Ask user where their projects are
    console.print()
    console.print(f"  [bold]{t('init_scanning_title', lang)}[/bold]")
    project_dir_raw = Prompt.ask(
        f"  [bold]?[/bold] {t('init_project_dir', lang)}",
        default="~/Documents",
        console=console,
    )
    project_dir = str(_resolve_project_dir(project_dir_raw))
    with console.status(f"  {t('init_discovering', lang)}"):
        if project_dir_raw.strip() == "~/Documents":
            projects = discover_projects()
        else:
            projects = discover_projects(roots=[Path(project_dir)])

    if not projects:
        console.print(f"  [dim]{t('init_no_projects', lang)}[/dim]")
        console.print()
        console.print(f"  {t('init_done', lang)}")
        console.print()
        return

    # Let user pick with checkboxes
    try:
        from InquirerPy import inquirer
        selected_paths = inquirer.checkbox(
            message=t("init_pick_projects", lang),
            choices=[{"name": f"{p['name']}  ({p['type']})  {p['path']}", "value": p["path"], "enabled": i < 5} for i, p in enumerate(projects)],
            cycle=False,
        ).execute()
    except (ImportError, Exception):
        # Fallback: show list and ask how many
        console.print(f"  {t('init_found_projects', lang, count=str(len(projects)))}")
        console.print()
        for i, p in enumerate(projects[:15], 1):
            console.print(f"    {i:2d}. [cyan]{p['name']}[/cyan] [dim]({p['type']})[/dim]")
        console.print()
        n = Prompt.ask(f"  [bold]?[/bold] {t('init_how_many', lang)}", default="5", console=console)
        try:
            n = min(int(n), len(projects))
        except ValueError:
            n = 5
        selected_paths = [p["path"] for p in projects[:n]]

    if not selected_paths:
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

    async def _run_init_scan() -> None:
        from neocortex.scan_cache import ScanCache
        from neocortex.scanner.analyzer import analyze_project

        cache = ScanCache(get_data_dir() / "scan_cache.json")
        all_skills = None
        for p_path in selected_paths:
            name = Path(p_path).name
            try:
                cached = cache.get(p_path)
                if cached is not None:
                    console.print(f"  [dim]{t('scan_cached', lang, name=name)}[/dim]")
                    skills = cached
                else:
                    with console.status(f"  {t('scan_project', lang, name=name)}"):
                        project_info = scanner.scan(p_path)
                        key_files = extract_key_files(
                            p_path,
                            max_lines=cfg.scan_settings.max_file_lines,
                            exclude_patterns=cfg.scan_settings.exclude_patterns,
                        )
                        skills = await analyze_project(project_info, key_files, provider)
                    cache.put(p_path, skills)

                    langs_str = ", ".join(
                        f"{ln} ({lines})" for ln, lines in sorted(project_info.languages.items(), key=lambda x: -x[1])
                    ) or "-"
                    console.print(f"  [dim]  {name}: {langs_str}[/dim]")

                if all_skills is not None:
                    all_skills = merge_profiles(all_skills, skills)
                else:
                    all_skills = skills
            except KeyboardInterrupt:
                console.print(f"\n  [yellow]{t('init_scan_interrupted', lang)}[/yellow]")
                break

        if all_skills is not None:
            prof.skills = all_skills
            from neocortex.config import filter_known_gaps
            filter_known_gaps(prof)
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


# Register commands from submodules
import neocortex.cmd_scan  # noqa: F401, E402
import neocortex.cmd_read  # noqa: F401, E402
import neocortex.cmd_learn  # noqa: F401, E402
import neocortex.cmd_knowledge  # noqa: F401, E402
import neocortex.cmd_import  # noqa: F401, E402
