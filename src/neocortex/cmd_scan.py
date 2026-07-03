"""Scan and profile commands."""

from __future__ import annotations

from neocortex._async import run_async
import json as json_lib
from pathlib import Path

import typer
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from neocortex.cli import (
    _format_display_name,
    _format_lines,
    _get_lang,
    _skill_bar,
    console,
    profile_app,
    smart_output,
)
from neocortex.i18n import t


@profile_app.command()
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
        from neocortex.scan_cache import ScanCache

        if not paths:
            return all_skills

        cache = ScanCache(get_data_dir() / "scan_cache.json")

        valid_paths: list[Path] = []
        for p in paths:
            resolved = Path(p).resolve()
            if not resolved.is_dir():
                console.print(f"  [red]{t('scan_not_found', lang, path=str(resolved))}[/red]")
            else:
                valid_paths.append(resolved)

        if not valid_paths:
            return all_skills

        results_table = Table(show_header=False, show_edge=False, pad_edge=False, padding=(0, 1))
        results_table.add_column("name", style="cyan", min_width=20)
        results_table.add_column("status")
        results_table.add_column("detail", style="dim")

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=30),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            overall = progress.add_task(
                t("scan_project", lang, name=""),
                total=len(valid_paths),
            )

            for resolved in valid_paths:
                progress.update(overall, description=f"  {resolved.name}")

                cached = cache.get(str(resolved))
                if cached is not None:
                    skills = cached
                    results_table.add_row(resolved.name, "[dim]cached[/dim]", "")
                else:
                    project_info = scanner.scan(str(resolved))

                    langs_str = ", ".join(
                        f"{ln} ({lines})"
                        for ln, lines in sorted(project_info.languages.items(), key=lambda x: -x[1])[:3]
                    )
                    frameworks_str = ", ".join(project_info.frameworks[:4]) if project_info.frameworks else ""

                    key_files = extract_key_files(
                        str(resolved),
                        max_lines=cfg.scan_settings.max_file_lines,
                        exclude_patterns=cfg.scan_settings.exclude_patterns,
                    )
                    skills = await analyze_project(project_info, key_files, provider)
                    cache.put(str(resolved), skills)

                    detail = frameworks_str or langs_str or "-"
                    results_table.add_row(resolved.name, "[green]✓[/green]", detail)

                if all_skills is not None:
                    all_skills = merge_profiles(all_skills, skills)
                else:
                    all_skills = skills

                progress.advance(overall)

        console.print()
        console.print(results_table)

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

        results_table = Table(show_header=False, show_edge=False, pad_edge=False, padding=(0, 1))
        results_table.add_column("name", style="cyan", min_width=20)
        results_table.add_column("status")
        results_table.add_column("detail", style="dim")

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=30),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            overall = progress.add_task(
                f"  GitHub ({len(repos)} repos)",
                total=len(repos),
            )

            for repo in repos:
                clone_path = None
                try:
                    progress.update(overall, description=f"  {repo['name']}")
                    clone_path = await clone_repo(repo["clone_url"], token)

                    project_info = scanner.scan(str(clone_path))

                    frameworks_str = ", ".join(project_info.frameworks[:4]) if project_info.frameworks else ""
                    langs_str = ", ".join(
                        f"{ln} ({lines})"
                        for ln, lines in sorted(project_info.languages.items(), key=lambda x: -x[1])[:3]
                    )

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

                    detail = frameworks_str or langs_str or "-"
                    results_table.add_row(repo["name"], "[green]✓[/green]", detail)

                except subprocess.CalledProcessError:
                    results_table.add_row(repo["name"], "[red]✗[/red]", "clone failed")
                finally:
                    if clone_path is not None:
                        cleanup_repo(clone_path)
                    progress.advance(overall)

        console.print()
        console.print(results_table)

        return all_skills

    async def _run_scan() -> None:
        all_skills = prof.skills if update else None

        all_skills = await _scan_local_paths(all_skills)
        all_skills = await _scan_github(all_skills)

        if all_skills is not None:
            prof.skills = all_skills

            from neocortex.config import filter_known_gaps
            filter_known_gaps(prof)

            save_profile(prof)

            from neocortex.growth import save_snapshot
            notes_count = len([p for p in get_notes_dir().rglob("*.md") if p.parts and "concepts" not in p.parts and "insights" not in p.parts and "diagrams" not in p.parts])
            save_snapshot(prof, get_data_dir(), notes_count)

            n_langs = len(all_skills.languages)
            n_domains = len(all_skills.domains)
            n_gaps = sum(len(d.gaps) for d in all_skills.domains.values())
            console.print()
            console.print(f"  [green bold]{t('scan_complete', lang)}[/green bold]")
            console.print(f"  [dim]{n_langs} languages · {n_domains} domains · {n_gaps} gaps[/dim]")

    run_async(_run_scan())


@profile_app.callback(invoke_without_command=True)
def profile(
    ctx: typer.Context,
    export: str = typer.Option(None, help="Export profile to file"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    edit: bool = typer.Option(False, "--edit", help="Open profile in editor"),
) -> None:
    """View, export, or edit your skill profile."""
    if ctx.invoked_subcommand is not None:
        return
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
                display = _format_display_name(name)
                bar = _skill_bar(skill.level, lang)
                line = Text()
                line.append(f"  {display:<20}", style="cyan")
                line.append_text(bar)
                console.print(line)
                if skill.gaps:
                    for gap in skill.gaps:
                        console.print(f"                      [dim]gap: {gap}[/dim]")

        if skills.integrations:
            console.print()
            console.print(f"  [bold]{t('profile_integrations', lang)}[/bold]")
            for name, skill in skills.integrations.items():
                display = _format_display_name(name)
                bar = _skill_bar(skill.level, lang)
                line = Text()
                line.append(f"  {display:<20}", style="cyan")
                line.append_text(bar)
                console.print(line)

        if skills.architecture:
            console.print()
            console.print(f"  [bold]{t('profile_architecture', lang)}[/bold]")
            for name, skill in skills.architecture.items():
                display = _format_display_name(name)
                bar = _skill_bar(skill.level, lang)
                line = Text()
                line.append(f"  {display:<20}", style="cyan")
                line.append_text(bar)
                console.print(line)

        console.print()

    smart_output(data, _human_format, json_output)
