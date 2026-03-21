"""Scan result cache — skip LLM calls for unchanged projects."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from neocortex.models import Skills


def _get_project_hash(project_path: str) -> str:
    """Get a hash representing the project's current state.

    Uses git HEAD if available, otherwise falls back to config file mtime.
    """
    p = Path(project_path)
    git_dir = p / ".git"
    if git_dir.exists():
        try:
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(p),
                capture_output=True,
                text=True,
                timeout=5,
            )
            dirty = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(p),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if head.returncode == 0:
                commit = head.stdout.strip()
                dirty_hash = str(hash(dirty.stdout)) if dirty.stdout else "clean"
                return f"{commit}:{dirty_hash}"
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Fallback: hash of config file mtimes
    config_files = [
        "package.json", "pyproject.toml", "requirements.txt", "go.mod",
        "Cargo.toml", "build.gradle", "pom.xml", "Gemfile", "composer.json",
    ]
    mtimes = []
    for name in config_files:
        f = p / name
        if f.exists():
            mtimes.append(f"{name}:{f.stat().st_mtime}")
    return "|".join(mtimes) if mtimes else "unknown"


class ScanCache:
    def __init__(self, cache_path: Path) -> None:
        self._path = cache_path
        self._data = self._load()

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, project_path: str) -> Skills | None:
        """Return cached Skills if project hasn't changed, else None."""
        project_hash = _get_project_hash(project_path)
        entry = self._data.get(project_path)
        if entry and entry.get("hash") == project_hash:
            try:
                return Skills(**entry["skills"])
            except Exception:
                return None
        return None

    def put(self, project_path: str, skills: Skills) -> None:
        """Cache scan results for a project."""
        project_hash = _get_project_hash(project_path)
        self._data[project_path] = {
            "hash": project_hash,
            "skills": skills.model_dump(mode="json"),
        }
        self._save()
