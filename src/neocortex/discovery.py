"""Auto-discover local projects for initial onboarding."""

from __future__ import annotations

from pathlib import Path

_CONFIG_FILES = {
    "package.json", "pyproject.toml", "requirements.txt", "Pipfile",
    "go.mod", "Cargo.toml", "build.gradle", "settings.gradle",
    "pom.xml", "Gemfile", "composer.json",
}

_SEARCH_ROOTS = [
    Path.home() / "Documents",
    Path.home() / "Projects",
    Path.home() / "projects",
    Path.home() / "repos",
    Path.home() / "code",
    Path.home() / "dev",
    Path.home() / "src",
    Path.home() / "workspace",
    Path.home() / "Work",
    Path.home() / "work",
]

_SKIP_NAMES = {
    "node_modules", ".git", "venv", ".venv", "__pycache__",
    "dist", "build", "target", ".next", ".nuxt", "vendor",
}


def discover_projects(max_depth: int = 3, max_results: int = 30) -> list[dict]:
    """Scan common directories for projects. Returns [{path, name, type}]."""
    found: list[dict] = []
    seen: set[str] = set()

    for root in _SEARCH_ROOTS:
        if not root.exists():
            continue
        _scan_dir(root, 0, max_depth, found, seen, max_results)
        if len(found) >= max_results:
            break

    found.sort(key=lambda p: p["name"].lower())
    return found[:max_results]


def _scan_dir(
    directory: Path,
    depth: int,
    max_depth: int,
    found: list[dict],
    seen: set[str],
    max_results: int,
) -> None:
    if depth > max_depth or len(found) >= max_results:
        return

    try:
        entries = sorted(directory.iterdir())
    except (PermissionError, OSError):
        return

    has_config = False
    for entry in entries:
        if entry.name in _CONFIG_FILES and entry.is_file():
            has_config = True
            break

    if has_config:
        resolved = str(directory.resolve())
        if resolved not in seen:
            seen.add(resolved)
            project_type = _detect_type(directory)
            found.append({
                "path": resolved,
                "name": directory.name,
                "type": project_type,
            })
        return

    for entry in entries:
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name in _SKIP_NAMES:
            continue
        _scan_dir(entry, depth + 1, max_depth, found, seen, max_results)


def _detect_type(directory: Path) -> str:
    if (directory / "pyproject.toml").exists() or (directory / "requirements.txt").exists():
        return "Python"
    if (directory / "package.json").exists():
        return "JS/TS"
    if (directory / "go.mod").exists():
        return "Go"
    if (directory / "Cargo.toml").exists():
        return "Rust"
    if (directory / "build.gradle").exists() or (directory / "settings.gradle").exists():
        return "Java/Kotlin"
    if (directory / "pom.xml").exists():
        return "Java"
    if (directory / "Gemfile").exists():
        return "Ruby"
    if (directory / "composer.json").exists():
        return "PHP"
    return "Unknown"
