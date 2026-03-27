"""Tests for the knowledge convergence module."""

from __future__ import annotations

import os
import time
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest

from neocortex.converger import detect_cadence, gather_recent_notes, generate_convergence_report
from neocortex.models import Language, Persona, Profile, Role, LearningGoal


class TestGatherRecentNotes:
    def test_collects_recent_files(self, tmp_path):
        today = date.today()
        f1 = tmp_path / "note1.md"
        f1.write_text("# First Note\nSome content here.", encoding="utf-8")

        f2 = tmp_path / "note2.md"
        f2.write_text("---\ntitle: Second Note\n---\nMore content.", encoding="utf-8")

        notes = gather_recent_notes(tmp_path, days=7)
        assert len(notes) == 2
        titles = {n["title"] for n in notes}
        assert "First Note" in titles
        assert "Second Note" in titles

    def test_excludes_old_files(self, tmp_path):
        f1 = tmp_path / "recent.md"
        f1.write_text("# Recent\nContent", encoding="utf-8")

        f2 = tmp_path / "old.md"
        f2.write_text("# Old\nContent", encoding="utf-8")
        old_time = time.time() - (15 * 86400)
        os.utime(f2, (old_time, old_time))

        notes = gather_recent_notes(tmp_path, days=7)
        assert len(notes) == 1
        assert notes[0]["title"] == "Recent"

    def test_empty_dir(self, tmp_path):
        notes = gather_recent_notes(tmp_path, days=7)
        assert notes == []

    def test_strips_frontmatter_from_preview(self, tmp_path):
        f = tmp_path / "note.md"
        f.write_text("---\ntitle: Test\ndate: 2026-01-01\n---\nActual content here.", encoding="utf-8")

        notes = gather_recent_notes(tmp_path, days=7)
        assert len(notes) == 1
        assert notes[0]["content"].startswith("Actual content here.")

    def test_falls_back_to_stem_for_title(self, tmp_path):
        f = tmp_path / "my-topic.md"
        f.write_text("No heading here, just plain text.", encoding="utf-8")

        notes = gather_recent_notes(tmp_path, days=7)
        assert len(notes) == 1
        assert notes[0]["title"] == "my-topic"

    def test_content_preview_truncated(self, tmp_path):
        f = tmp_path / "long.md"
        f.write_text("# Long\n" + "x" * 5000, encoding="utf-8")

        notes = gather_recent_notes(tmp_path, days=7)
        assert len(notes) == 1
        assert len(notes[0]["content"]) <= 2000

    def test_ignores_non_md_files(self, tmp_path):
        (tmp_path / "note.md").write_text("# Note\nContent", encoding="utf-8")
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        (tmp_path / "data.json").write_text("{}", encoding="utf-8")

        notes = gather_recent_notes(tmp_path, days=7)
        assert len(notes) == 1


class TestDetectCadence:
    def test_flash_for_few_notes(self):
        assert detect_cadence([{}] * 1) == "flash"
        assert detect_cadence([{}] * 5) == "flash"

    def test_weekly_for_moderate_notes(self):
        assert detect_cadence([{}] * 6) == "weekly"
        assert detect_cadence([{}] * 20) == "weekly"

    def test_monthly_for_many_notes(self):
        assert detect_cadence([{}] * 21) == "monthly"
        assert detect_cadence([{}] * 50) == "monthly"


class TestGenerateConvergenceReport:
    @pytest.mark.asyncio
    async def test_calls_provider_and_returns_report(self):
        mock_provider = AsyncMock()
        mock_provider.chat.return_value = "## Themes Discovered\nSome themes here."

        prof = Profile(persona=Persona(
            role=Role.BACKEND,
            learning_goal=LearningGoal.SYSTEM_DESIGN,
        ))
        notes = [
            {"title": "Note A", "date": "2026-03-20", "content": "Content about databases."},
            {"title": "Note B", "date": "2026-03-22", "content": "Content about caching."},
        ]

        result = await generate_convergence_report(notes, "weekly", prof, mock_provider, Language.EN)

        assert result == "## Themes Discovered\nSome themes here."
        mock_provider.chat.assert_called_once()
        call_args = mock_provider.chat.call_args[0][0]
        assert call_args[0]["role"] == "system"
        assert call_args[1]["role"] == "user"
        assert "Note A" in call_args[1]["content"]
        assert "Note B" in call_args[1]["content"]
        assert "Output in English." in call_args[1]["content"]

    @pytest.mark.asyncio
    async def test_chinese_language_instruction(self):
        mock_provider = AsyncMock()
        mock_provider.chat.return_value = "report"

        prof = Profile()
        notes = [{"title": "T", "date": "2026-03-20", "content": "C"}]

        await generate_convergence_report(notes, "flash", prof, mock_provider, Language.ZH)

        call_args = mock_provider.chat.call_args[0][0]
        assert "用中文输出。" in call_args[1]["content"]

    @pytest.mark.asyncio
    async def test_cadence_appears_in_prompt(self):
        mock_provider = AsyncMock()
        mock_provider.chat.return_value = "report"

        prof = Profile()
        notes = [{"title": "T", "date": "2026-03-20", "content": "C"}]

        await generate_convergence_report(notes, "monthly", prof, mock_provider)

        call_args = mock_provider.chat.call_args[0][0]
        assert "monthly" in call_args[1]["content"]
        assert "monthly synthesis" in call_args[1]["content"]

    @pytest.mark.asyncio
    async def test_persona_defaults_when_empty(self):
        mock_provider = AsyncMock()
        mock_provider.chat.return_value = "report"

        prof = Profile()
        notes = [{"title": "T", "date": "2026-03-20", "content": "C"}]

        await generate_convergence_report(notes, "flash", prof, mock_provider)

        call_args = mock_provider.chat.call_args[0][0]
        assert "developer" in call_args[1]["content"]
        assert "level up" in call_args[1]["content"]
