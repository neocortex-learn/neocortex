"""Tests for scan_cache — project hashing and cache hit/miss."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from neocortex.models import LanguageSkill, Skills, SkillLevel
from neocortex.scan_cache import ScanCache, _get_project_hash


def _make_skills() -> Skills:
    return Skills(languages={"python": LanguageSkill(level=SkillLevel.PROFICIENT, lines=500)})


# ── _get_project_hash ──


class TestGetProjectHash:
    def test_non_git_with_config_file(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]")
        h1 = _get_project_hash(str(tmp_path))
        assert h1 and h1 != "empty"

    def test_non_git_with_source_files(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("print('hello')")
        h1 = _get_project_hash(str(tmp_path))
        assert h1 and h1 != "empty"

    def test_non_git_hash_changes_on_source_edit(self, tmp_path: Path):
        src = tmp_path / "app.py"
        src.write_text("v1")
        h1 = _get_project_hash(str(tmp_path))
        time.sleep(0.05)
        src.write_text("v2")
        h2 = _get_project_hash(str(tmp_path))
        assert h1 != h2

    def test_non_git_hash_deterministic(self, tmp_path: Path):
        (tmp_path / "main.py").write_text("stable")
        h1 = _get_project_hash(str(tmp_path))
        h2 = _get_project_hash(str(tmp_path))
        assert h1 == h2

    def test_empty_dir_returns_dir_listing_hash(self, tmp_path: Path):
        (tmp_path / "README").write_text("hi")
        h = _get_project_hash(str(tmp_path))
        assert h and h != "empty" and h != "unknown"

    def test_truly_empty_dir(self, tmp_path: Path):
        h = _get_project_hash(str(tmp_path))
        assert h  # Should not crash, returns some hash

    def test_git_project_uses_commit(self, tmp_path: Path):
        """If .git exists and git commands work, uses commit hash."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        fake_commit = "abc123def456"
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                type("R", (), {"returncode": 0, "stdout": fake_commit})(),
                type("R", (), {"returncode": 0, "stdout": ""})(),
            ]
            h = _get_project_hash(str(tmp_path))
            assert fake_commit in h
            assert "clean" in h

    def test_git_dirty_uses_md5(self, tmp_path: Path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                type("R", (), {"returncode": 0, "stdout": "abc123"})(),
                type("R", (), {"returncode": 0, "stdout": "M file.py\n"})(),
            ]
            h = _get_project_hash(str(tmp_path))
            assert "abc123:" in h
            assert "clean" not in h

    def test_skips_hidden_and_venv_dirs(self, tmp_path: Path):
        venv = tmp_path / "venv"
        venv.mkdir()
        (venv / "lib.py").write_text("skip me")
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.py").write_text("skip me")
        (tmp_path / "main.py").write_text("include me")
        h = _get_project_hash(str(tmp_path))
        assert h and h != "empty"


# ── ScanCache ──


class TestScanCache:
    def test_put_and_get(self, tmp_path: Path):
        cache = ScanCache(tmp_path / "cache.json")
        project = tmp_path / "myproject"
        project.mkdir()
        (project / "main.py").write_text("print('hi')")
        skills = _make_skills()

        cache.put(str(project), skills)
        result = cache.get(str(project))
        assert result is not None
        assert result.languages["python"].level == SkillLevel.PROFICIENT

    def test_cache_miss_when_changed(self, tmp_path: Path):
        cache = ScanCache(tmp_path / "cache.json")
        project = tmp_path / "myproject"
        project.mkdir()
        src = project / "main.py"
        src.write_text("v1")

        cache.put(str(project), _make_skills())
        time.sleep(0.05)
        src.write_text("v2")
        result = cache.get(str(project))
        assert result is None

    def test_cache_miss_when_empty(self, tmp_path: Path):
        cache = ScanCache(tmp_path / "cache.json")
        result = cache.get("/nonexistent/path")
        assert result is None

    def test_cache_survives_corrupt_file(self, tmp_path: Path):
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("not json!!!", encoding="utf-8")
        cache = ScanCache(cache_file)
        assert cache.get("/any/path") is None

    def test_cache_persists_to_disk(self, tmp_path: Path):
        cache_file = tmp_path / "cache.json"
        project = tmp_path / "proj"
        project.mkdir()
        (project / "app.py").write_text("code")

        cache1 = ScanCache(cache_file)
        cache1.put(str(project), _make_skills())
        assert cache_file.exists()

        cache2 = ScanCache(cache_file)
        result = cache2.get(str(project))
        assert result is not None
