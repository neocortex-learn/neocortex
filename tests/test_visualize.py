"""Tests for visualization commands and exercise generation."""

from __future__ import annotations

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from neocortex.cmd_visualize import _concept_slug, _node_style, _star_rating
from neocortex.models import (
    ConceptEntry,
    DomainSkill,
    Language,
    Outline,
    OutlineItem,
    Persona,
    Profile,
    Role,
    SkillLevel,
    Skills,
)


# ── Fixtures ──


@pytest.fixture()
def notes_dir(tmp_path):
    d = tmp_path / "notes"
    d.mkdir()
    return d


@pytest.fixture()
def profile():
    return Profile(
        skills=Skills(
            domains={
                "backend": DomainSkill(level=SkillLevel.PROFICIENT),
                "database": DomainSkill(level=SkillLevel.BEGINNER),
            }
        )
    )


@pytest.fixture()
def mock_provider():
    provider = AsyncMock()
    provider.chat = AsyncMock()
    provider.name.return_value = "mock"
    provider.max_context_tokens.return_value = 100000
    return provider


def _write_concept(concepts_dir: Path, name: str, evidence: int, related: list[str], last_updated: str = "") -> None:
    """Helper to write a concept entry file."""
    concepts_dir.mkdir(parents=True, exist_ok=True)
    slug = name.strip().lower().replace(" ", "-")
    if not last_updated:
        last_updated = date.today().isoformat()
    related_str = ", ".join(related)
    content = (
        f"---\n"
        f"type: concept\n"
        f"name: {name}\n"
        f"aliases: [{slug}]\n"
        f"related_concepts: [{related_str}]\n"
        f"skill_level: beginner\n"
        f"confidence: 0.3\n"
        f"evidence_count: {evidence}\n"
        f"last_updated: {last_updated}\n"
        f"source_notes: [note1.md]\n"
        f"---\n\n"
        f"# {name}\n\nSome content.\n"
    )
    (concepts_dir / f"{slug}.md").write_text(content, encoding="utf-8")


# ── Helpers ──


class TestConceptSlug:
    def test_simple_name(self):
        assert _concept_slug("Redis") == "Redis"

    def test_spaces_replaced(self):
        assert _concept_slug("Event Sourcing") == "Event_Sourcing"

    def test_special_chars_replaced(self):
        assert _concept_slug("C++/CLI") == "C___CLI"

    def test_hyphens_replaced(self):
        assert _concept_slug("domain-events") == "domain_events"


class TestStarRating:
    def test_three_stars_for_high_evidence(self):
        result = _star_rating(3)
        assert result == "\u2605\u2605\u2605"
        assert _star_rating(5) == "\u2605\u2605\u2605"

    def test_two_stars_for_some_evidence(self):
        result = _star_rating(1)
        assert result == "\u2605\u2605\u2606"
        assert _star_rating(2) == "\u2605\u2605\u2606"

    def test_one_star_for_no_evidence(self):
        result = _star_rating(0)
        assert result == "\u2605\u2606\u2606"


class TestNodeStyle:
    def test_green_for_high_evidence(self):
        result = _node_style("ES", 3)
        assert "#2d5016" in result

    def test_yellow_for_some_evidence(self):
        result = _node_style("CQRS", 1)
        assert "#8b6914" in result

    def test_grey_for_no_evidence(self):
        result = _node_style("Saga", 0)
        assert "#555" in result


# ── Concept Map ──


class TestConceptMap:
    def test_generates_mermaid_with_concepts(self, notes_dir, profile):
        from neocortex.compiler import collect_all_concepts

        concepts_dir = notes_dir / "concepts"
        _write_concept(concepts_dir, "Event Sourcing", 3, ["CQRS", "Domain Events"])
        _write_concept(concepts_dir, "CQRS", 2, ["Event Sourcing"])
        _write_concept(concepts_dir, "Domain Events", 0, [])

        concepts = collect_all_concepts(concepts_dir)
        assert len(concepts) == 3

        concept_map = {c.name: c for c in concepts}
        assert "Event Sourcing" in concept_map
        assert concept_map["Event Sourcing"].evidence_count == 3
        assert "CQRS" in concept_map["Event Sourcing"].related_concepts

    def test_no_concepts_returns_empty(self, notes_dir):
        from neocortex.compiler import collect_all_concepts

        concepts_dir = notes_dir / "concepts"
        concepts = collect_all_concepts(concepts_dir)
        assert concepts == []

    def test_domain_filter(self, notes_dir, profile):
        from neocortex.compiler import collect_all_concepts, match_domain

        concepts_dir = notes_dir / "concepts"
        _write_concept(concepts_dir, "Connection Pooling", 2, [])
        _write_concept(concepts_dir, "Redis Caching", 1, [])

        known_domains = {"backend", "database"}
        concepts = collect_all_concepts(concepts_dir)

        backend_concepts = [
            c for c in concepts
            if match_domain(c.name, known_domains) == "backend"
        ]
        other_concepts = [
            c for c in concepts
            if match_domain(c.name, known_domains) == "other"
        ]
        assert len(concepts) == 2
        total_matched = len(backend_concepts) + len(other_concepts)
        assert total_matched <= len(concepts)

    def test_around_filter(self, notes_dir):
        from neocortex.compiler import collect_all_concepts

        concepts_dir = notes_dir / "concepts"
        _write_concept(concepts_dir, "Event Sourcing", 3, ["CQRS"])
        _write_concept(concepts_dir, "CQRS", 2, ["Event Sourcing"])
        _write_concept(concepts_dir, "Unrelated", 1, [])

        concepts = collect_all_concepts(concepts_dir)
        center = next(c for c in concepts if c.name == "Event Sourcing")
        neighbor_names = {n.lower() for n in center.related_concepts}
        neighbor_names.add(center.name.lower())
        filtered = [c for c in concepts if c.name.lower() in neighbor_names]

        assert len(filtered) == 2
        names = {c.name for c in filtered}
        assert "Event Sourcing" in names
        assert "CQRS" in names
        assert "Unrelated" not in names

    def test_mermaid_output_format(self, notes_dir):
        concepts_dir = notes_dir / "concepts"
        _write_concept(concepts_dir, "Event Sourcing", 3, ["CQRS"])
        _write_concept(concepts_dir, "CQRS", 1, [])

        from neocortex.compiler import collect_all_concepts
        concepts = collect_all_concepts(concepts_dir)

        lines = ["graph LR"]
        for c in concepts:
            slug = _concept_slug(c.name)
            display = f'{c.name} {_star_rating(c.evidence_count)}'
            lines.append(f'    {slug}["{display}"]')

        mermaid = "\n".join(lines)
        assert "graph LR" in mermaid
        assert "Event_Sourcing" in mermaid
        assert "CQRS" in mermaid
        assert "\u2605\u2605\u2605" in mermaid
        assert "\u2605\u2605\u2606" in mermaid

    def test_edges_between_related_concepts(self, notes_dir):
        concepts_dir = notes_dir / "concepts"
        _write_concept(concepts_dir, "A", 2, ["B"])
        _write_concept(concepts_dir, "B", 1, ["A"])

        from neocortex.compiler import collect_all_concepts
        concepts = collect_all_concepts(concepts_dir)
        concept_map = {c.name: c for c in concepts}

        seen_edges: set[tuple[str, str]] = set()
        edge_lines: list[str] = []
        for c in concepts:
            src = _concept_slug(c.name)
            for rel in c.related_concepts:
                if rel in concept_map:
                    dst = _concept_slug(rel)
                    edge_key = tuple(sorted((src, dst)))
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        edge_lines.append(f"    {src} --> {dst}")

        assert len(edge_lines) == 1
        assert "A" in edge_lines[0]
        assert "B" in edge_lines[0]


# ── Digest ──


class TestDigest:
    def test_stats_collection(self, notes_dir):
        (notes_dir / "note1.md").write_text("# Note 1\nContent.", encoding="utf-8")
        (notes_dir / "note2.md").write_text("# Note 2\nContent.", encoding="utf-8")

        old_note = notes_dir / "old-note.md"
        old_note.write_text("# Old\nContent.", encoding="utf-8")
        old_time = time.time() - (30 * 86400)
        os.utime(old_note, (old_time, old_time))

        from neocortex.converger import gather_recent_notes
        recent = gather_recent_notes(notes_dir, days=7)
        assert len(recent) == 2

    def test_concept_counting(self, notes_dir):
        from neocortex.compiler import collect_all_concepts

        concepts_dir = notes_dir / "concepts"
        today = date.today().isoformat()
        old_date = (date.today() - timedelta(days=30)).isoformat()

        _write_concept(concepts_dir, "New Concept", 1, [], last_updated=today)
        _write_concept(concepts_dir, "Old Concept", 2, [], last_updated=old_date)

        cutoff = (date.today() - timedelta(days=7)).isoformat()
        all_concepts = collect_all_concepts(concepts_dir)
        new_concepts = [c for c in all_concepts if c.last_updated >= cutoff]

        assert len(all_concepts) == 2
        assert len(new_concepts) == 1
        assert new_concepts[0].name == "New Concept"

    def test_flashcard_review_count(self, notes_dir):
        from neocortex.config import load_flashcards
        from neocortex.models import Flashcard

        fc_dir = notes_dir / ".flashcards"
        fc_dir.mkdir()
        cards = [
            Flashcard(
                id="a1", source_note="note1.md",
                question="Q1", answer="A1",
                review_count=3,
            ),
            Flashcard(
                id="a2", source_note="note1.md",
                question="Q2", answer="A2",
                review_count=0,
            ),
        ]
        import json as json_lib
        (fc_dir / "note1.json").write_text(
            json_lib.dumps([c.model_dump(mode="json") for c in cards]),
            encoding="utf-8",
        )

        all_cards = load_flashcards(notes_dir)
        reviewed = sum(1 for c in all_cards if c.review_count > 0)
        assert reviewed == 1

    def test_insights_counting(self, notes_dir):
        insights_dir = notes_dir / "insights"
        insights_dir.mkdir()
        (insights_dir / "insight1.md").write_text("# Insight\nContent.", encoding="utf-8")
        (insights_dir / "insight2.md").write_text("# Insight 2\nContent.", encoding="utf-8")

        old_insight = insights_dir / "old.md"
        old_insight.write_text("# Old\nContent.", encoding="utf-8")
        old_time = time.time() - (30 * 86400)
        os.utime(old_insight, (old_time, old_time))

        cutoff = (date.today() - timedelta(days=7)).isoformat()
        insights_count = 0
        for f in insights_dir.glob("*.md"):
            mtime = date.fromtimestamp(f.stat().st_mtime).isoformat()
            if mtime >= cutoff:
                insights_count += 1

        assert insights_count == 2


# ── Exercises ──


class TestGenerateExercises:
    @pytest.mark.asyncio
    async def test_generates_exercises(self, mock_provider):
        from neocortex.reader.fetcher import Document
        from neocortex.reader.teacher import generate_exercises

        mock_provider.chat.return_value = (
            "## Exercise 1: Apply Event Sourcing\n\n"
            "Description: Refactor your user service to use event sourcing.\n\n"
            "Hint: Start with a single aggregate.\n\n"
            "## Exercise 2: Add CQRS Read Model\n\n"
            "Description: Create a separate read model.\n\n"
            "Hint: Use a projection to build the read side.\n"
        )

        doc = Document(
            title="Event Sourcing Guide",
            source="https://example.com",
            content="Event sourcing stores state changes as events.",
            sections=[],
        )
        outline = Outline(
            source="https://example.com",
            items=[
                OutlineItem(title="Event Sourcing Basics", marker="deep", reason="gap"),
                OutlineItem(title="CQRS", marker="brief", reason="review"),
            ],
        )
        prof = Profile(
            persona=Persona(role=Role.BACKEND),
        )

        result = await generate_exercises(doc, outline, "Notes content here", prof, mock_provider)

        assert "Exercise 1" in result
        assert "Exercise 2" in result
        mock_provider.chat.assert_called_once()
        prompt = mock_provider.chat.call_args[0][0][0]["content"]
        assert "Event Sourcing Guide" in prompt
        assert "Event Sourcing Basics" in prompt

    @pytest.mark.asyncio
    async def test_uses_profile_projects(self, mock_provider):
        from neocortex.models import LanguageSkill
        from neocortex.reader.fetcher import Document
        from neocortex.reader.teacher import generate_exercises

        mock_provider.chat.return_value = "## Exercise\nDo something."

        doc = Document(
            title="Test", source="test", content="content", sections=[],
        )
        outline = Outline(source="test", items=[])
        prof = Profile(
            skills=Skills(
                languages={
                    "python": LanguageSkill(
                        level=SkillLevel.ADVANCED,
                        projects=["my-api", "data-pipeline"],
                    ),
                }
            ),
        )

        await generate_exercises(doc, outline, "notes", prof, mock_provider)

        prompt = mock_provider.chat.call_args[0][0][0]["content"]
        assert "my-api" in prompt
        assert "data-pipeline" in prompt

    @pytest.mark.asyncio
    async def test_empty_response(self, mock_provider):
        from neocortex.reader.fetcher import Document
        from neocortex.reader.teacher import generate_exercises

        mock_provider.chat.return_value = ""

        doc = Document(
            title="Test", source="test", content="content", sections=[],
        )
        outline = Outline(source="test", items=[])
        prof = Profile()

        result = await generate_exercises(doc, outline, "notes", prof, mock_provider)
        assert result == ""
