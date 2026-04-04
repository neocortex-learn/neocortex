"""Tests for three-layer knowledge flashcards and relationship cards."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from neocortex.models import ConceptEntry, ConceptRef, Flashcard, Language


# ── Flashcard model backward compatibility ──


class TestFlashcardBackwardCompat:
    def test_default_knowledge_layer(self):
        card = Flashcard(
            id="abc",
            source_note="note.md",
            question="Q?",
            answer="A.",
        )
        assert card.knowledge_layer == "conceptual"
        assert card.card_type == "standard"

    def test_explicit_knowledge_layer(self):
        card = Flashcard(
            id="abc",
            source_note="note.md",
            question="Q?",
            answer="A.",
            knowledge_layer="factual",
            card_type="relationship",
        )
        assert card.knowledge_layer == "factual"
        assert card.card_type == "relationship"

    def test_deserialize_without_new_fields(self):
        raw = {
            "id": "abc",
            "source_note": "note.md",
            "question": "Q?",
            "answer": "A.",
            "concept": "test",
            "difficulty": "easy",
            "interval": 1,
            "ease_factor": 2.5,
            "next_review": "",
            "review_count": 0,
            "last_review": None,
        }
        card = Flashcard.model_validate(raw)
        assert card.knowledge_layer == "conceptual"
        assert card.card_type == "standard"

    def test_serialize_includes_new_fields(self):
        card = Flashcard(
            id="abc",
            source_note="note.md",
            question="Q?",
            answer="A.",
            knowledge_layer="procedural",
            card_type="relationship",
        )
        data = card.model_dump()
        assert data["knowledge_layer"] == "procedural"
        assert data["card_type"] == "relationship"


# ── generate_flashcards returns knowledge_layer ──


class TestGenerateFlashcardsLayer:
    @pytest.mark.asyncio
    async def test_returns_knowledge_layer(self):
        from neocortex.models import Profile
        from neocortex.reader.fetcher import Document, Section
        from neocortex.models import Outline, OutlineItem
        from neocortex.reader.teacher import generate_flashcards

        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=json.dumps([
            {
                "question": "What is X?",
                "answer": "X is Y.",
                "concept": "X",
                "difficulty": "easy",
                "knowledge_layer": "factual",
            },
            {
                "question": "Why use X over Z?",
                "answer": "Because...",
                "concept": "X",
                "difficulty": "medium",
                "knowledge_layer": "conceptual",
            },
            {
                "question": "How to implement X?",
                "answer": "Step 1...",
                "concept": "X",
                "difficulty": "hard",
                "knowledge_layer": "procedural",
            },
        ]))

        doc = Document(
            title="Test",
            source="http://example.com",
            content="Some content",
            sections=[Section(title="Intro", content="Intro content", level=1)],
        )
        outline = Outline(
            source="http://example.com",
            items=[OutlineItem(title="Intro", marker="deep", reason="key topic")],
        )
        profile = Profile()

        cards = await generate_flashcards(doc, outline, "Some notes", profile, provider)
        assert len(cards) == 3
        assert cards[0]["knowledge_layer"] == "factual"
        assert cards[1]["knowledge_layer"] == "conceptual"
        assert cards[2]["knowledge_layer"] == "procedural"

    @pytest.mark.asyncio
    async def test_defaults_to_conceptual_when_missing(self):
        from neocortex.models import Profile
        from neocortex.reader.fetcher import Document, Section
        from neocortex.models import Outline, OutlineItem
        from neocortex.reader.teacher import generate_flashcards

        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=json.dumps([
            {
                "question": "Q?",
                "answer": "A.",
                "concept": "X",
                "difficulty": "easy",
            },
        ]))

        doc = Document(
            title="Test",
            source="http://example.com",
            content="Some content",
            sections=[Section(title="Intro", content="Intro content", level=1)],
        )
        outline = Outline(
            source="http://example.com",
            items=[OutlineItem(title="Intro", marker="deep", reason="key topic")],
        )
        profile = Profile()

        cards = await generate_flashcards(doc, outline, "notes", profile, provider)
        assert len(cards) == 1
        assert cards[0]["knowledge_layer"] == "conceptual"


# ── Relationship card generation ──


@pytest.fixture()
def notes_dir(tmp_path):
    d = tmp_path / "notes"
    d.mkdir()
    return d


@pytest.fixture()
def mock_provider():
    provider = AsyncMock()
    provider.chat = AsyncMock()
    return provider


def _create_concept_file(concepts_dir: Path, name: str, entry: ConceptEntry) -> None:
    """Write a minimal concept file with frontmatter."""
    concepts_dir.mkdir(parents=True, exist_ok=True)
    slug = name.strip().lower().replace(" ", "-")
    path = concepts_dir / f"{slug}.md"
    related = ", ".join(entry.related_concepts)
    sources = ", ".join(entry.source_notes)
    content = (
        f"---\n"
        f"type: concept\n"
        f"name: {name}\n"
        f"aliases: []\n"
        f"related_concepts: [{related}]\n"
        f"skill_level: beginner\n"
        f"confidence: 0.3\n"
        f"evidence_count: {entry.evidence_count}\n"
        f"last_updated: {date.today().isoformat()}\n"
        f"source_notes: [{sources}]\n"
        f"---\n"
        f"\n# {name}\n\nContent.\n"
    )
    path.write_text(content, encoding="utf-8")


class TestRelationshipCards:
    @pytest.mark.asyncio
    async def test_generates_relationship_cards(self, notes_dir, mock_provider):
        from neocortex.compiler import _generate_relationship_cards

        concepts_dir = notes_dir / "concepts"
        _create_concept_file(concepts_dir, "Event Sourcing", ConceptEntry(
            name="Event Sourcing",
            evidence_count=3,
            related_concepts=["CQRS"],
            source_notes=["a.md", "b.md", "c.md"],
        ))
        _create_concept_file(concepts_dir, "CQRS", ConceptEntry(
            name="CQRS",
            evidence_count=2,
            related_concepts=["Event Sourcing"],
            source_notes=["a.md", "b.md"],
        ))

        mock_provider.chat.return_value = json.dumps([
            {
                "question": "How do Event Sourcing and CQRS work together?",
                "answer": "They complement each other.",
                "concept_a": "CQRS",
                "concept_b": "Event Sourcing",
            },
        ])

        concepts = [
            ConceptRef(name="Event Sourcing", related_to=["CQRS"]),
            ConceptRef(name="CQRS", related_to=["Event Sourcing"]),
        ]

        await _generate_relationship_cards(notes_dir, concepts, mock_provider, Language.EN)

        rel_path = notes_dir / ".flashcards" / "_relationships.json"
        assert rel_path.exists()

        data = json.loads(rel_path.read_text(encoding="utf-8"))
        assert len(data) == 1
        card = Flashcard.model_validate(data[0])
        assert card.card_type == "relationship"
        assert card.knowledge_layer == "conceptual"
        assert "CQRS" in card.concept
        assert "Event Sourcing" in card.concept
        assert " <> " in card.concept

    @pytest.mark.asyncio
    async def test_skips_when_evidence_too_low(self, notes_dir, mock_provider):
        from neocortex.compiler import _generate_relationship_cards

        concepts_dir = notes_dir / "concepts"
        _create_concept_file(concepts_dir, "Event Sourcing", ConceptEntry(
            name="Event Sourcing",
            evidence_count=1,
            related_concepts=["CQRS"],
            source_notes=["a.md"],
        ))
        _create_concept_file(concepts_dir, "CQRS", ConceptEntry(
            name="CQRS",
            evidence_count=1,
            related_concepts=["Event Sourcing"],
            source_notes=["a.md"],
        ))

        concepts = [
            ConceptRef(name="Event Sourcing", related_to=["CQRS"]),
            ConceptRef(name="CQRS", related_to=["Event Sourcing"]),
        ]

        await _generate_relationship_cards(notes_dir, concepts, mock_provider, Language.EN)

        rel_path = notes_dir / ".flashcards" / "_relationships.json"
        assert not rel_path.exists()
        mock_provider.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_fewer_than_two_eligible(self, notes_dir, mock_provider):
        from neocortex.compiler import _generate_relationship_cards

        concepts_dir = notes_dir / "concepts"
        _create_concept_file(concepts_dir, "Redis", ConceptEntry(
            name="Redis",
            evidence_count=5,
            related_concepts=[],
            source_notes=["a.md", "b.md", "c.md", "d.md", "e.md"],
        ))

        concepts = [ConceptRef(name="Redis", related_to=[])]

        await _generate_relationship_cards(notes_dir, concepts, mock_provider, Language.EN)

        rel_path = notes_dir / ".flashcards" / "_relationships.json"
        assert not rel_path.exists()
        mock_provider.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_deduplicates_existing_pairs(self, notes_dir, mock_provider):
        from neocortex.compiler import _generate_relationship_cards
        from neocortex.config import save_flashcards

        concepts_dir = notes_dir / "concepts"
        _create_concept_file(concepts_dir, "Event Sourcing", ConceptEntry(
            name="Event Sourcing",
            evidence_count=3,
            related_concepts=["CQRS"],
            source_notes=["a.md", "b.md", "c.md"],
        ))
        _create_concept_file(concepts_dir, "CQRS", ConceptEntry(
            name="CQRS",
            evidence_count=2,
            related_concepts=["Event Sourcing"],
            source_notes=["a.md", "b.md"],
        ))

        existing_card = Flashcard(
            id="existing",
            source_note="",
            question="Existing Q?",
            answer="Existing A.",
            concept="CQRS <> Event Sourcing",
            card_type="relationship",
            knowledge_layer="conceptual",
            next_review=date.today().isoformat(),
        )
        save_flashcards(notes_dir, "_relationships", [existing_card])

        concepts = [
            ConceptRef(name="Event Sourcing", related_to=["CQRS"]),
            ConceptRef(name="CQRS", related_to=["Event Sourcing"]),
        ]

        await _generate_relationship_cards(notes_dir, concepts, mock_provider, Language.EN)

        mock_provider.chat.assert_not_called()

        rel_path = notes_dir / ".flashcards" / "_relationships.json"
        data = json.loads(rel_path.read_text(encoding="utf-8"))
        assert len(data) == 1

    @pytest.mark.asyncio
    async def test_no_related_concepts_skips(self, notes_dir, mock_provider):
        from neocortex.compiler import _generate_relationship_cards

        concepts_dir = notes_dir / "concepts"
        _create_concept_file(concepts_dir, "Redis", ConceptEntry(
            name="Redis",
            evidence_count=3,
            related_concepts=[],
            source_notes=["a.md", "b.md", "c.md"],
        ))
        _create_concept_file(concepts_dir, "Kafka", ConceptEntry(
            name="Kafka",
            evidence_count=2,
            related_concepts=[],
            source_notes=["a.md", "b.md"],
        ))

        concepts = [
            ConceptRef(name="Redis", related_to=[]),
            ConceptRef(name="Kafka", related_to=[]),
        ]

        await _generate_relationship_cards(notes_dir, concepts, mock_provider, Language.EN)

        rel_path = notes_dir / ".flashcards" / "_relationships.json"
        assert not rel_path.exists()
        mock_provider.chat.assert_not_called()
