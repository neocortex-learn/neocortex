"""Tests for the concept compilation engine."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.compiler import (
    CompileCache,
    collect_all_concepts,
    _parse_concept_frontmatter,
    compile_all,
    compile_note,
    detect_conflicts,
    extract_claims,
    extract_concepts,
    generate_concept_entry,
    generate_index,
    generate_overview,
    insert_wikilinks,
)
from neocortex.models import (
    CompileResult,
    ConceptEntry,
    ConceptRef,
    DomainSkill,
    Language,
    Profile,
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


# ── Extract concepts ──


class TestExtractConcepts:
    @pytest.mark.asyncio
    async def test_extract_concepts_basic(self, mock_provider):
        mock_provider.chat.return_value = json.dumps([
            {
                "name": "Event Sourcing",
                "definition_brief": "Store state changes as events",
                "related_to": ["CQRS"],
            },
            {
                "name": "CQRS",
                "definition_brief": "Separate read and write models",
                "related_to": ["Event Sourcing"],
            },
        ])

        refs = await extract_concepts("Some note content about Event Sourcing and CQRS", mock_provider)
        assert len(refs) == 2
        assert refs[0].name == "Event Sourcing"
        assert refs[0].definition_brief == "Store state changes as events"
        assert refs[0].related_to == ["CQRS"]
        assert refs[1].name == "CQRS"

    @pytest.mark.asyncio
    async def test_extract_concepts_with_markdown_fences(self, mock_provider):
        mock_provider.chat.return_value = '```json\n[{"name": "Redis", "definition_brief": "In-memory store", "related_to": []}]\n```'

        refs = await extract_concepts("Redis notes", mock_provider)
        assert len(refs) == 1
        assert refs[0].name == "Redis"

    @pytest.mark.asyncio
    async def test_extract_concepts_invalid_json(self, mock_provider):
        mock_provider.chat.return_value = "This is not JSON at all"

        refs = await extract_concepts("Some content", mock_provider)
        assert refs == []

    @pytest.mark.asyncio
    async def test_extract_concepts_empty_list(self, mock_provider):
        mock_provider.chat.return_value = "[]"

        refs = await extract_concepts("Short content", mock_provider)
        assert refs == []

    @pytest.mark.asyncio
    async def test_extract_concepts_missing_name(self, mock_provider):
        mock_provider.chat.return_value = json.dumps([
            {"definition_brief": "No name here"},
            {"name": "Valid", "definition_brief": "Has a name"},
        ])

        refs = await extract_concepts("Some content", mock_provider)
        assert len(refs) == 1
        assert refs[0].name == "Valid"

    @pytest.mark.asyncio
    async def test_extract_concepts_truncates_content(self, mock_provider):
        mock_provider.chat.return_value = "[]"
        long_content = "x" * 10000

        await extract_concepts(long_content, mock_provider)
        call_args = mock_provider.chat.call_args
        user_msg = call_args[0][0][1]["content"]
        assert len(user_msg) <= 3000


# ── Insert wikilinks ──


class TestInsertWikilinks:
    def test_basic_insertion(self):
        content = "Event Sourcing is a great pattern."
        result = insert_wikilinks(content, ["Event Sourcing"])
        assert "[[Event Sourcing|Event Sourcing]]" in result

    def test_case_insensitive(self):
        content = "event sourcing is useful."
        result = insert_wikilinks(content, ["Event Sourcing"])
        assert "[[Event Sourcing|event sourcing]]" in result

    def test_only_first_occurrence(self):
        content = "Event Sourcing is great. Event Sourcing is also complex."
        result = insert_wikilinks(content, ["Event Sourcing"])
        assert result.count("[[Event Sourcing") == 1

    def test_skip_frontmatter(self):
        content = "---\ntitle: Event Sourcing\n---\nEvent Sourcing is great."
        result = insert_wikilinks(content, ["Event Sourcing"])
        lines = result.split("\n")
        assert lines[1] == "title: Event Sourcing"
        assert "[[Event Sourcing" in lines[3]

    def test_skip_code_blocks(self):
        content = "Intro.\n```\nEvent Sourcing code\n```\nEvent Sourcing is great."
        result = insert_wikilinks(content, ["Event Sourcing"])
        lines = result.split("\n")
        assert "[[" not in lines[2]
        assert "[[Event Sourcing" in lines[4]

    def test_skip_headings(self):
        content = "# Event Sourcing\nEvent Sourcing is a pattern."
        result = insert_wikilinks(content, ["Event Sourcing"])
        lines = result.split("\n")
        assert lines[0] == "# Event Sourcing"
        assert "[[Event Sourcing" in lines[1]

    def test_skip_existing_wikilinks(self):
        content = "Already linked [[Event Sourcing]] here."
        result = insert_wikilinks(content, ["Event Sourcing"])
        assert result.count("[[Event Sourcing") == 1

    def test_multiple_concepts(self):
        content = "Event Sourcing and CQRS are related patterns."
        result = insert_wikilinks(content, ["Event Sourcing", "CQRS"])
        assert "[[Event Sourcing|Event Sourcing]]" in result
        assert "[[CQRS|CQRS]]" in result

    def test_aliases(self):
        content = "event-sourcing is useful."
        result = insert_wikilinks(
            content, ["Event Sourcing"],
            aliases={"Event Sourcing": ["event-sourcing"]},
        )
        assert "[[Event Sourcing|event-sourcing]]" in result

    def test_empty_concept_list(self):
        content = "No changes expected."
        result = insert_wikilinks(content, [])
        assert result == content

    def test_frontmatter_with_code_block(self):
        content = "---\ntitle: Test\n---\n\n```python\nclass EventSourcing:\n    pass\n```\n\nEvent Sourcing is great."
        result = insert_wikilinks(content, ["Event Sourcing"])
        lines = result.split("\n")
        assert "[[" not in lines[5]
        assert "[[Event Sourcing" in lines[9]

    def test_preserves_original_case(self):
        content = "CQRS is a pattern."
        result = insert_wikilinks(content, ["CQRS"])
        assert "[[CQRS|CQRS]]" in result

    def test_no_match_returns_unchanged(self):
        content = "Nothing to link here."
        result = insert_wikilinks(content, ["Event Sourcing"])
        assert result == content


# ── INDEX.md generation ──


class TestGenerateIndex:
    def test_basic_index(self, notes_dir, profile):
        (notes_dir / "note1-2026-04-01.md").write_text(
            "# First Note\nSome content.", encoding="utf-8",
        )
        (notes_dir / "note2-2026-04-02.md").write_text(
            "# Second Note\nMore content.", encoding="utf-8",
        )

        concepts = [
            ConceptEntry(
                name="Event Sourcing",
                aliases=["event-sourcing"],
                evidence_count=3,
                source_notes=["note1-2026-04-01.md", "note2-2026-04-02.md", "note3.md"],
            ),
            ConceptEntry(
                name="CQRS",
                aliases=["cqrs"],
                evidence_count=1,
                source_notes=["note1-2026-04-01.md"],
            ),
        ]

        result = generate_index(notes_dir, concepts, profile, Language.EN)
        assert "Knowledge Base" in result
        assert "2 notes" in result
        assert "2 concepts" in result
        assert "[[Event Sourcing]]" in result
        assert "[[CQRS]]" in result
        assert "\u2605\u2605\u2605" in result
        assert "\u2605\u2605\u2606" in result

    def test_index_chinese(self, notes_dir, profile):
        (notes_dir / "note1.md").write_text("# Test\nContent.", encoding="utf-8")
        concepts = [
            ConceptEntry(name="Redis", evidence_count=1, source_notes=["note1.md"]),
        ]
        result = generate_index(notes_dir, concepts, profile, Language.ZH)
        assert "知识库" in result

    def test_index_skips_subdirs(self, notes_dir, profile):
        (notes_dir / "note.md").write_text("# Note\nContent.", encoding="utf-8")
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "concept.md").write_text("# Concept\nContent.", encoding="utf-8")

        concepts = [ConceptEntry(name="Test", evidence_count=0, source_notes=[])]
        result = generate_index(notes_dir, concepts, profile, Language.EN)
        assert "1 notes" in result

    def test_index_star_ratings(self, notes_dir, profile):
        (notes_dir / "x.md").write_text("# X\nContent.", encoding="utf-8")
        concepts = [
            ConceptEntry(name="A", evidence_count=5, source_notes=["a.md", "b.md", "c.md", "d.md", "e.md"]),
            ConceptEntry(name="B", evidence_count=2, source_notes=["a.md", "b.md"]),
            ConceptEntry(name="C", evidence_count=0, source_notes=[]),
        ]
        result = generate_index(notes_dir, concepts, profile, Language.EN)
        lines = result.split("\n")
        a_line = next(l for l in lines if "[[A]]" in l)
        b_line = next(l for l in lines if "[[B]]" in l)
        c_line = next(l for l in lines if "[[C]]" in l)
        assert "\u2605\u2605\u2605" in a_line
        assert "\u2605\u2605\u2606" in b_line
        assert "\u2605\u2606\u2606" in c_line

    def test_index_coverage_section(self, notes_dir, profile):
        (notes_dir / "x.md").write_text("# X\nContent.", encoding="utf-8")
        concepts = [
            ConceptEntry(name="A", evidence_count=3, source_notes=["a.md", "b.md", "c.md"]),
            ConceptEntry(name="B", evidence_count=1, source_notes=["a.md"]),
            ConceptEntry(name="C", evidence_count=0, source_notes=[]),
        ]
        result = generate_index(notes_dir, concepts, profile, Language.EN)
        assert "1 mastered" in result
        assert "1 learning" in result
        assert "1 gaps" in result


# ── Compile cache ──


class TestCompileCache:
    def test_new_file_is_changed(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        note = tmp_path / "note.md"
        note.write_text("Hello", encoding="utf-8")

        cache = CompileCache(cache_path)
        assert cache.is_changed(note) is True

    def test_unchanged_after_update(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        note = tmp_path / "note.md"
        note.write_text("Hello", encoding="utf-8")

        cache = CompileCache(cache_path)
        cache.update(note)
        cache.save()

        cache2 = CompileCache(cache_path)
        assert cache2.is_changed(note) is False

    def test_changed_after_modification(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        note = tmp_path / "note.md"
        note.write_text("Hello", encoding="utf-8")

        cache = CompileCache(cache_path)
        cache.update(note)
        cache.save()

        note.write_text("World", encoding="utf-8")
        cache2 = CompileCache(cache_path)
        assert cache2.is_changed(note) is True

    def test_missing_file_is_changed(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        note = tmp_path / "nonexistent.md"

        cache = CompileCache(cache_path)
        assert cache.is_changed(note) is True

    def test_corrupt_cache_file(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        cache_path.write_text("not json", encoding="utf-8")
        note = tmp_path / "note.md"
        note.write_text("Hello", encoding="utf-8")

        cache = CompileCache(cache_path)
        assert cache.is_changed(note) is True


# ── Concept frontmatter parsing ──


class TestParseFrontmatter:
    def test_parse_basic(self):
        content = (
            "---\n"
            "type: concept\n"
            "name: Event Sourcing\n"
            "aliases: [event-sourcing, event_sourcing]\n"
            "related_concepts: [CQRS, Domain Events]\n"
            "skill_level: beginner\n"
            "confidence: 0.5\n"
            "evidence_count: 2\n"
            "last_updated: 2026-04-01\n"
            "source_notes: [note1.md, note2.md]\n"
            "---\n"
            "\n# Event Sourcing\n"
        )
        entry = _parse_concept_frontmatter(content, "fallback")
        assert entry.name == "Event Sourcing"
        assert entry.aliases == ["event-sourcing", "event_sourcing"]
        assert entry.related_concepts == ["CQRS", "Domain Events"]
        assert entry.skill_level == SkillLevel.BEGINNER
        assert entry.confidence == 0.5
        assert entry.evidence_count == 2
        assert entry.source_notes == ["note1.md", "note2.md"]

    def test_parse_no_frontmatter(self):
        content = "# Just a heading\nNo frontmatter."
        entry = _parse_concept_frontmatter(content, "fallback")
        assert entry.name == "fallback"

    def test_parse_empty_lists(self):
        content = (
            "---\n"
            "name: Test\n"
            "aliases: []\n"
            "source_notes: []\n"
            "---\n"
        )
        entry = _parse_concept_frontmatter(content, "fallback")
        assert entry.aliases == []
        assert entry.source_notes == []


# ── Incremental compile (integration) ──


class TestCompileNote:
    @pytest.mark.asyncio
    async def test_compile_note_creates_concepts(self, notes_dir, profile, mock_provider):
        note = notes_dir / "test-note-2026-04-01.md"
        note.write_text(
            "---\ntitle: Test Note\n---\n\n# Test Note\n\nContent about Event Sourcing and CQRS.",
            encoding="utf-8",
        )

        mock_provider.chat.side_effect = [
            json.dumps([
                {"name": "Event Sourcing", "definition_brief": "Store events", "related_to": ["CQRS"]},
                {"name": "CQRS", "definition_brief": "Separate reads and writes", "related_to": []},
            ]),
            "## One-liner\nStore state changes as events.\n\n## Core Points\n- Append only\n\n## Open Questions\n- How to handle snapshots?",
            "## One-liner\nSeparate command and query.\n\n## Core Points\n- Read model\n\n## Open Questions\n- When to use?",
        ]

        result = await compile_note(note, notes_dir, profile, mock_provider, Language.EN)

        assert result.notes_processed == 1
        assert result.concepts_created == 2
        assert result.index_updated is True

        concepts_dir = notes_dir / "concepts"
        assert concepts_dir.exists()
        assert (concepts_dir / "event-sourcing.md").exists()
        assert (concepts_dir / "cqrs.md").exists()

        index_path = notes_dir / "INDEX.md"
        assert index_path.exists()

    @pytest.mark.asyncio
    async def test_compile_note_no_concepts(self, notes_dir, profile, mock_provider):
        note = notes_dir / "empty-note.md"
        note.write_text("---\ntitle: Empty\n---\n\nNothing here.", encoding="utf-8")

        mock_provider.chat.return_value = "[]"

        result = await compile_note(note, notes_dir, profile, mock_provider, Language.EN)
        assert result.notes_processed == 0
        assert result.concepts_created == 0

    @pytest.mark.asyncio
    async def test_compile_note_inserts_wikilinks(self, notes_dir, profile, mock_provider):
        note = notes_dir / "test-wikilink.md"
        note.write_text(
            "---\ntitle: Test\n---\n\nEvent Sourcing is important.",
            encoding="utf-8",
        )

        mock_provider.chat.side_effect = [
            json.dumps([
                {"name": "Event Sourcing", "definition_brief": "Store events", "related_to": []},
            ]),
            "## One-liner\nBody.\n\n## Core Points\n- Point.\n\n## Open Questions\n- Q?",
        ]

        result = await compile_note(note, notes_dir, profile, mock_provider, Language.EN)

        content = note.read_text(encoding="utf-8")
        assert "[[Event Sourcing" in content


# ── Full compile ──


class TestCompileAll:
    @pytest.mark.asyncio
    async def test_compile_all_basic(self, notes_dir, profile, mock_provider):
        (notes_dir / "note1.md").write_text(
            "---\ntitle: Note 1\n---\n\n# Note 1\nContent about Redis.",
            encoding="utf-8",
        )
        (notes_dir / "note2.md").write_text(
            "---\ntitle: Note 2\n---\n\n# Note 2\nContent about Kafka.",
            encoding="utf-8",
        )

        mock_provider.chat.side_effect = [
            json.dumps([{"name": "Redis", "definition_brief": "In-memory store", "related_to": []}]),
            json.dumps([{"name": "Kafka", "definition_brief": "Event streaming", "related_to": []}]),
            "## One-liner\nRedis body.\n\n## Core Points\n- Fast.\n\n## Open Questions\n- Persistence?",
            "## One-liner\nKafka body.\n\n## Core Points\n- Distributed.\n\n## Open Questions\n- Ordering?",
        ]

        with patch("neocortex.config.get_data_dir", return_value=notes_dir.parent):
            result = await compile_all(notes_dir, profile, mock_provider, Language.EN, force=True)

        assert result.notes_processed == 2
        assert result.concepts_created == 2
        assert result.index_updated is True

    @pytest.mark.asyncio
    async def test_compile_all_uses_cache(self, notes_dir, profile, mock_provider):
        note = notes_dir / "cached-note.md"
        note.write_text(
            "---\ntitle: Cached\n---\n\n# Cached\nOld content.",
            encoding="utf-8",
        )

        mock_provider.chat.side_effect = [
            json.dumps([{"name": "Test", "definition_brief": "Desc", "related_to": []}]),
            "## One-liner\nBody.\n\n## Core Points\n- P.\n\n## Open Questions\n- Q?",
        ]

        data_dir = notes_dir.parent
        with patch("neocortex.config.get_data_dir", return_value=data_dir):
            result1 = await compile_all(notes_dir, profile, mock_provider, Language.EN, force=True)

        assert result1.notes_processed == 1

        mock_provider.chat.reset_mock()
        mock_provider.chat.return_value = "[]"

        with patch("neocortex.config.get_data_dir", return_value=data_dir):
            result2 = await compile_all(notes_dir, profile, mock_provider, Language.EN, force=False)

        assert result2.notes_processed == 0
        mock_provider.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_compile_all_skips_concepts_dir(self, notes_dir, profile, mock_provider):
        (notes_dir / "note.md").write_text(
            "---\ntitle: Note\n---\n\n# Note\nContent.",
            encoding="utf-8",
        )
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "existing.md").write_text(
            "---\nname: Existing\n---\n# Existing",
            encoding="utf-8",
        )

        mock_provider.chat.side_effect = [
            json.dumps([{"name": "New", "definition_brief": "Desc", "related_to": []}]),
            "## One-liner\nBody.\n\n## Core Points\n- P.\n\n## Open Questions\n- Q?",
        ]

        with patch("neocortex.config.get_data_dir", return_value=notes_dir.parent):
            result = await compile_all(notes_dir, profile, mock_provider, Language.EN, force=True)

        assert result.notes_processed == 1

    @pytest.mark.asyncio
    async def test_compile_all_empty_dir(self, notes_dir, profile, mock_provider):
        with patch("neocortex.config.get_data_dir", return_value=notes_dir.parent):
            result = await compile_all(notes_dir, profile, mock_provider, Language.EN)

        assert result.notes_processed == 0
        assert result.concepts_created == 0

    @pytest.mark.asyncio
    async def test_compile_all_progress_callback(self, notes_dir, profile, mock_provider):
        (notes_dir / "note.md").write_text(
            "---\ntitle: Note\n---\n\n# Note\nContent.",
            encoding="utf-8",
        )

        mock_provider.chat.side_effect = [
            json.dumps([{"name": "Test", "definition_brief": "Desc", "related_to": []}]),
            "## One-liner\nBody.\n\n## Core Points\n- P.\n\n## Open Questions\n- Q?",
        ]

        progress_calls = []

        def on_progress(current: int, total: int) -> None:
            progress_calls.append((current, total))

        with patch("neocortex.config.get_data_dir", return_value=notes_dir.parent):
            await compile_all(notes_dir, profile, mock_provider, Language.EN, on_progress=on_progress, force=True)

        assert len(progress_calls) >= 1
        assert progress_calls[0] == (1, 1)


# ── Collect all concepts ──


class TestCollectAllConcepts:
    def test_collects_from_concepts_dir(self, notes_dir):
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "redis.md").write_text(
            "---\ntype: concept\nname: Redis\nevidence_count: 3\n"
            "source_notes: [note1.md]\n---\n\n# Redis\nIn-memory store.",
            encoding="utf-8",
        )
        (concepts_dir / "kafka.md").write_text(
            "---\ntype: concept\nname: Kafka\nevidence_count: 1\n"
            "source_notes: []\n---\n\n# Kafka\nEvent streaming.",
            encoding="utf-8",
        )

        entries = collect_all_concepts(concepts_dir)
        assert len(entries) == 2
        names = {e.name for e in entries}
        assert names == {"Redis", "Kafka"}

    def test_empty_dir(self, notes_dir):
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        entries = collect_all_concepts(concepts_dir)
        assert entries == []

    def test_nonexistent_dir(self, notes_dir):
        entries = collect_all_concepts(notes_dir / "nonexistent")
        assert entries == []

    def test_skips_unreadable_files(self, notes_dir):
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        bad = concepts_dir / "bad.md"
        bad.write_bytes(b"\x80\x81\x82")  # invalid utf-8

        (concepts_dir / "good.md").write_text(
            "---\nname: Good\n---\n# Good", encoding="utf-8",
        )

        entries = collect_all_concepts(concepts_dir)
        assert len(entries) >= 1
        assert any(e.name == "Good" for e in entries)

    def test_fallback_name_from_stem(self, notes_dir):
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "my-concept.md").write_text(
            "# Just a heading\nNo frontmatter name.", encoding="utf-8",
        )

        entries = collect_all_concepts(concepts_dir)
        assert len(entries) == 1
        assert entries[0].name == "my-concept"


# ── Extract claims ──


class TestExtractClaims:
    @pytest.mark.asyncio
    async def test_extract_claims_basic(self, mock_provider):
        mock_provider.chat.return_value = json.dumps([
            {"claim": "Redis supports pub/sub", "concept": "Redis", "context": "messaging"},
            {"claim": "Redis is single-threaded", "concept": "Redis", "context": "architecture"},
        ])

        claims = await extract_claims("Redis notes content", mock_provider)
        assert len(claims) == 2
        assert claims[0]["claim"] == "Redis supports pub/sub"
        assert claims[0]["concept"] == "Redis"

    @pytest.mark.asyncio
    async def test_extract_claims_invalid_json(self, mock_provider):
        mock_provider.chat.return_value = "not json at all"
        claims = await extract_claims("content", mock_provider)
        assert claims == []

    @pytest.mark.asyncio
    async def test_extract_claims_strips_markdown_fences(self, mock_provider):
        mock_provider.chat.return_value = '```json\n[{"claim": "X is Y", "concept": "X"}]\n```'
        claims = await extract_claims("content", mock_provider)
        assert len(claims) == 1
        assert claims[0]["claim"] == "X is Y"

    @pytest.mark.asyncio
    async def test_extract_claims_skips_items_without_claim(self, mock_provider):
        mock_provider.chat.return_value = json.dumps([
            {"concept": "Redis"},  # no "claim" key
            {"claim": "Valid claim", "concept": "Test"},
        ])
        claims = await extract_claims("content", mock_provider)
        assert len(claims) == 1
        assert claims[0]["claim"] == "Valid claim"

    @pytest.mark.asyncio
    async def test_extract_claims_non_list_returns_empty(self, mock_provider):
        mock_provider.chat.return_value = '{"claim": "not a list"}'
        claims = await extract_claims("content", mock_provider)
        assert claims == []

    @pytest.mark.asyncio
    async def test_extract_claims_missing_optional_fields(self, mock_provider):
        mock_provider.chat.return_value = json.dumps([
            {"claim": "Bare claim"},
        ])
        claims = await extract_claims("content", mock_provider)
        assert len(claims) == 1
        assert claims[0]["concept"] == ""
        assert claims[0]["context"] == ""


# ── Detect conflicts ──


class TestDetectConflicts:
    @pytest.mark.asyncio
    async def test_no_matching_concepts_returns_empty(self, mock_provider):
        new_claims = [{"claim": "X", "concept": "Redis"}]
        existing_claims = {"Kafka": [{"claim": "Y"}]}

        conflicts = await detect_conflicts(new_claims, existing_claims, mock_provider)
        assert conflicts == []
        mock_provider.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_detect_genuine_conflict(self, mock_provider):
        mock_provider.chat.return_value = json.dumps([
            {
                "pair_index": 0,
                "type": "genuine",
                "explanation": "Contradicts",
                "resolution_hint": "Check version",
            }
        ])

        new_claims = [{"claim": "Redis is multi-threaded", "concept": "Redis"}]
        existing_claims = {"redis": [{"claim": "Redis is single-threaded", "source": "old-note.md"}]}

        conflicts = await detect_conflicts(new_claims, existing_claims, mock_provider)
        assert len(conflicts) == 1
        assert conflicts[0]["type"] == "genuine"
        assert conflicts[0]["claim_a"] == "Redis is single-threaded"
        assert conflicts[0]["claim_b"] == "Redis is multi-threaded"

    @pytest.mark.asyncio
    async def test_detect_no_conflict(self, mock_provider):
        mock_provider.chat.return_value = "[]"

        new_claims = [{"claim": "Redis supports strings", "concept": "Redis"}]
        existing_claims = {"redis": [{"claim": "Redis supports hashes"}]}

        conflicts = await detect_conflicts(new_claims, existing_claims, mock_provider)
        assert conflicts == []

    @pytest.mark.asyncio
    async def test_detect_conflicts_invalid_json(self, mock_provider):
        mock_provider.chat.return_value = "not json"

        new_claims = [{"claim": "X", "concept": "Redis"}]
        existing_claims = {"redis": [{"claim": "Y"}]}

        conflicts = await detect_conflicts(new_claims, existing_claims, mock_provider)
        assert conflicts == []

    @pytest.mark.asyncio
    async def test_detect_conflicts_invalid_pair_index(self, mock_provider):
        mock_provider.chat.return_value = json.dumps([
            {"pair_index": 999, "type": "genuine", "explanation": "Bad index"},
        ])

        new_claims = [{"claim": "X", "concept": "Redis"}]
        existing_claims = {"redis": [{"claim": "Y"}]}

        conflicts = await detect_conflicts(new_claims, existing_claims, mock_provider)
        assert conflicts == []


# ── Generate concept entry ──


class TestGenerateConceptEntry:
    @pytest.mark.asyncio
    async def test_generates_frontmatter_and_body(self, mock_provider, profile):
        mock_provider.chat.return_value = (
            "## One-liner\nIn-memory data store.\n\n"
            "## Core Points\n- Fast lookups\n\n"
            "## Open Questions\n- When to use vs Memcached?"
        )

        source_notes = [
            {"filename": "redis-basics.md", "title": "Redis Basics", "content_preview": "Redis is..."},
        ]

        result = await generate_concept_entry(
            "Redis", source_notes, ["Memcached"], profile, mock_provider, Language.EN,
        )

        assert "---" in result
        assert "name: Redis" in result
        assert "type: concept" in result
        assert "evidence_count: 1" in result
        assert '\"redis-basics.md\"' in result
        assert "[[Memcached]]" in result
        assert "In-memory data store" in result

    @pytest.mark.asyncio
    async def test_generates_chinese_sections(self, mock_provider, profile):
        mock_provider.chat.return_value = (
            "## 一句话理解\n内存数据存储。\n\n"
            "## 核心要点\n- 快速查询\n\n"
            "## 开放问题\n- 何时使用？"
        )

        result = await generate_concept_entry(
            "Redis", [{"filename": "a.md", "title": "A"}],
            [], profile, mock_provider, Language.ZH,
        )

        assert "来源笔记" in result
        assert "内存数据存储" in result


# ── Generate overview ──


class TestGenerateOverview:
    @pytest.mark.asyncio
    async def test_creates_overview_file(self, notes_dir, profile, mock_provider):
        mock_provider.chat.return_value = (
            "## Knowledge Map\nYou focus on backend.\n\n"
            "## Cross-Domain Connections\nRedis + Kafka.\n\n"
            "## Belief Evolution\nNone.\n\n"
            "## Blind Spots\nFrontend.\n\n"
            "## Suggested Directions\nLearn React."
        )

        concepts = [
            ConceptEntry(name="Redis", evidence_count=3, source_notes=["a.md"]),
            ConceptEntry(name="Kafka", evidence_count=2, source_notes=["b.md"]),
        ]

        with patch("neocortex.config.load_belief_changes", return_value=[]):
            await generate_overview(notes_dir, concepts, profile, mock_provider, Language.EN)

        overview_path = notes_dir / "overview.md"
        assert overview_path.exists()
        content = overview_path.read_text(encoding="utf-8")
        assert "type: overview" in content
        assert "concepts: 2" in content
        assert "Knowledge Map" in content

    @pytest.mark.asyncio
    async def test_overview_skips_empty_concepts(self, notes_dir, profile, mock_provider):
        await generate_overview(notes_dir, [], profile, mock_provider, Language.EN)
        assert not (notes_dir / "overview.md").exists()
        mock_provider.chat.assert_not_called()
