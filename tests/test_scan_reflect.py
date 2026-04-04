from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from neocortex.cmd_read import _write_reflection_to_frontmatter
from neocortex.models import (
    Calibration,
    DomainSkill,
    Language,
    Persona,
    Profile,
    Skills,
)
from neocortex.reader.fetcher import Document, Section
from neocortex.reader.teacher import generate_scan_summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(**kwargs) -> Profile:
    defaults = {
        "persona": Persona(language=Language.EN),
        "calibration": Calibration(),
    }
    defaults.update(kwargs)
    return Profile(**defaults)


def _make_provider_mock(response: str) -> AsyncMock:
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=response)
    provider.max_context_tokens = MagicMock(return_value=128_000)
    provider.name = MagicMock(return_value="mock")
    return provider


def _make_doc(title: str = "Test Article", content: str = "Some content") -> Document:
    return Document(
        title=title,
        content=content,
        source="https://example.com/article",
        sections=[Section(title=title, content=content, level=1)],
    )


def _make_note(tmp_path: Path, content: str | None = None) -> Path:
    if content is None:
        content = (
            '---\ntitle: "Test"\nsource: "https://example.com"\ndate: 2026-01-01\n---\n\n# Test\n\nBody text.\n'
        )
    note = tmp_path / "test-note.md"
    note.write_text(content, encoding="utf-8")
    return note


# ===========================================================================
# 1. generate_scan_summary — valid JSON
# ===========================================================================


class TestGenerateScanSummary:
    @pytest.mark.asyncio
    async def test_returns_correct_format(self):
        llm_response = json.dumps({
            "summary": "Great intro to event sourcing",
            "priority": "P0",
            "relevant_gaps": ["event-sourcing", "cqrs"],
        })
        provider = _make_provider_mock(llm_response)
        profile = _make_profile(
            skills=Skills(domains={"backend": DomainSkill(gaps=["event-sourcing", "cqrs"])}),
        )
        doc = _make_doc()

        result = await generate_scan_summary(doc, profile, provider)

        assert result["summary"] == "Great intro to event sourcing"
        assert result["priority"] == "P0"
        assert result["relevant_gaps"] == ["event-sourcing", "cqrs"]

    @pytest.mark.asyncio
    async def test_p1_priority(self):
        llm_response = json.dumps({
            "summary": "Tangentially useful",
            "priority": "P1",
            "relevant_gaps": ["docker"],
        })
        provider = _make_provider_mock(llm_response)
        result = await generate_scan_summary(_make_doc(), _make_profile(), provider)

        assert result["priority"] == "P1"

    @pytest.mark.asyncio
    async def test_invalid_priority_normalizes_to_p2(self):
        llm_response = json.dumps({
            "summary": "Something",
            "priority": "HIGH",
            "relevant_gaps": [],
        })
        provider = _make_provider_mock(llm_response)
        result = await generate_scan_summary(_make_doc(), _make_profile(), provider)

        assert result["priority"] == "P2"

    @pytest.mark.asyncio
    async def test_empty_gaps_list(self):
        llm_response = json.dumps({
            "summary": "Fun read",
            "priority": "P2",
            "relevant_gaps": [],
        })
        provider = _make_provider_mock(llm_response)
        result = await generate_scan_summary(_make_doc(), _make_profile(), provider)

        assert result["relevant_gaps"] == []


# ===========================================================================
# 2. generate_scan_summary — degraded / malformed JSON
# ===========================================================================


class TestGenerateScanSummaryDegraded:
    @pytest.mark.asyncio
    async def test_completely_invalid_json_falls_back(self):
        provider = _make_provider_mock("This is not JSON at all")
        doc = _make_doc(title="Fallback Title")
        result = await generate_scan_summary(doc, _make_profile(), provider)

        assert result["summary"] == "Fallback Title"
        assert result["priority"] == "P2"
        assert result["relevant_gaps"] == []

    @pytest.mark.asyncio
    async def test_markdown_wrapped_json(self):
        inner = json.dumps({
            "summary": "Wrapped result",
            "priority": "P0",
            "relevant_gaps": ["testing"],
        })
        response = f"```json\n{inner}\n```"
        provider = _make_provider_mock(response)
        result = await generate_scan_summary(_make_doc(), _make_profile(), provider)

        assert result["summary"] == "Wrapped result"
        assert result["priority"] == "P0"

    @pytest.mark.asyncio
    async def test_missing_fields_use_defaults(self):
        provider = _make_provider_mock(json.dumps({"summary": "Only summary"}))
        result = await generate_scan_summary(_make_doc(), _make_profile(), provider)

        assert result["summary"] == "Only summary"
        assert result["priority"] == "P2"
        assert result["relevant_gaps"] == []

    @pytest.mark.asyncio
    async def test_non_list_relevant_gaps_normalized(self):
        provider = _make_provider_mock(json.dumps({
            "summary": "X",
            "priority": "P1",
            "relevant_gaps": "not-a-list",
        }))
        result = await generate_scan_summary(_make_doc(), _make_profile(), provider)

        assert result["relevant_gaps"] == []


# ===========================================================================
# 3. Reflection — frontmatter writing
# ===========================================================================


class TestWriteReflectionToFrontmatter:
    def test_inserts_reflection_into_frontmatter(self, tmp_path: Path):
        note = _make_note(tmp_path)

        reflection = {
            "surprise": "Didn't expect snapshot strategy to matter",
            "connection": "Related to CQRS read model rebuilding",
            "application": "Try event stream in gap_progress",
        }
        _write_reflection_to_frontmatter(note, reflection)

        content = note.read_text(encoding="utf-8")
        assert "reflection:" in content
        assert 'surprise: "Didn' in content
        assert 'connection: "Related' in content
        assert 'application: "Try' in content
        assert content.index("reflection:") < content.index("---\n\n#")

    def test_partial_reflection(self, tmp_path: Path):
        note = _make_note(tmp_path)

        _write_reflection_to_frontmatter(note, {"surprise": "Only this"})

        content = note.read_text(encoding="utf-8")
        assert "reflection:" in content
        assert 'surprise: "Only this"' in content
        assert "connection:" not in content
        assert "application:" not in content

    def test_no_frontmatter_does_nothing(self, tmp_path: Path):
        note = _make_note(tmp_path, content="# No frontmatter\n\nJust content.\n")
        original = note.read_text(encoding="utf-8")

        _write_reflection_to_frontmatter(note, {"surprise": "test"})

        assert note.read_text(encoding="utf-8") == original

    def test_preserves_existing_content(self, tmp_path: Path):
        note = _make_note(tmp_path)
        original = note.read_text(encoding="utf-8")

        _write_reflection_to_frontmatter(note, {"application": "use at work"})

        content = note.read_text(encoding="utf-8")
        assert 'title: "Test"' in content
        assert "# Test" in content
        assert "Body text." in content


# ===========================================================================
# 4. Reflection — skip scenario
# ===========================================================================


class TestReflectionSkip:
    def test_empty_reflection_not_written(self, tmp_path: Path):
        note = _make_note(tmp_path)
        original = note.read_text(encoding="utf-8")

        _write_reflection_to_frontmatter(note, {})

        assert note.read_text(encoding="utf-8") == original

    def test_whitespace_only_values_filtered(self, tmp_path: Path):
        """_collect_reflection strips values before calling _write, so empty dict = no write.
        This test validates _write_reflection_to_frontmatter with an empty dict."""
        note = _make_note(tmp_path)
        original = note.read_text(encoding="utf-8")

        _write_reflection_to_frontmatter(note, {})

        assert note.read_text(encoding="utf-8") == original


# ===========================================================================
# 5. Scan mode does not generate note file
# ===========================================================================


class TestScanModeNoNoteFile:
    @pytest.mark.asyncio
    async def test_scan_summary_does_not_write_files(self, tmp_path: Path):
        """generate_scan_summary only returns data — it never touches the filesystem."""
        llm_response = json.dumps({
            "summary": "Quick scan",
            "priority": "P1",
            "relevant_gaps": [],
        })
        provider = _make_provider_mock(llm_response)
        doc = _make_doc()

        files_before = set(tmp_path.iterdir())

        await generate_scan_summary(doc, _make_profile(), provider)

        files_after = set(tmp_path.iterdir())
        assert files_before == files_after
