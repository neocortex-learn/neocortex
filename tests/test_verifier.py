"""Tests for the knowledge base fidelity verification engine."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from neocortex.models import (
    AtomicFact,
    ConceptEntry,
    ConceptVerification,
    Evidence,
    FactCheck,
    FactVerdict,
    VerifyReport,
)
from neocortex.verifier import (
    VerifyCache,
    _extract_keywords,
    assign_verdicts,
    compute_fidelity_score,
    decompose_atomic_facts,
    extract_concept_body,
    find_evidence_keyword,
    update_concept_confidence,
    verify_concept,
)


# ── extract_concept_body ──


class TestExtractConceptBody:
    def test_strips_frontmatter(self):
        content = "---\nname: X\nconfidence: 0.5\n---\n# X\n\nBody text here."
        assert extract_concept_body(content) == "Body text here."

    def test_strips_top_level_heading(self):
        content = "# Event Sourcing\n\nEvent sourcing stores state changes as events."
        result = extract_concept_body(content)
        assert "# Event Sourcing" not in result
        assert "stores state changes" in result

    def test_skips_source_notes_section(self):
        content = (
            "# X\n\nBody.\n\n"
            "## Source Notes\n- [[note-a]]\n- [[note-b]]\n\n"
            "## Related Concepts\n- [[Y]]"
        )
        result = extract_concept_body(content)
        assert "Body." in result
        assert "note-a" not in result
        assert "[[Y]]" not in result

    def test_skips_chinese_source_notes_heading(self):
        content = "# X\n\nBody.\n\n## 来源笔记\n- [[note-a]]"
        result = extract_concept_body(content)
        assert "Body." in result
        assert "note-a" not in result

    def test_keeps_other_sections(self):
        content = "# X\n\n## Definition\nSome definition text."
        result = extract_concept_body(content)
        assert "## Definition" in result
        assert "Some definition text." in result

    def test_empty_content(self):
        assert extract_concept_body("") == ""


# ── _extract_keywords ──


class TestExtractKeywords:
    def test_english_removes_stop_words(self):
        keywords = _extract_keywords("The system is a distributed cache")
        assert "the" not in keywords
        assert "is" not in keywords
        assert "system" in keywords
        assert "distributed" in keywords
        assert "cache" in keywords

    def test_english_single_char_words_dropped(self):
        keywords = _extract_keywords("a b I am go")
        # single-char tokens never match [a-zA-Z]{2,}
        assert all(len(k) >= 2 for k in keywords)

    def test_chinese_bigrams(self):
        keywords = _extract_keywords("事件溯源")
        # after removing stop chars (none here), bigrams over 4 chars
        assert "事件" in keywords
        assert "件溯" in keywords
        assert "溯源" in keywords

    def test_chinese_filters_stop_chars(self):
        keywords = _extract_keywords("这是一个概念")
        # stop chars filtered before bigram extraction
        assert "这是" not in keywords

    def test_empty_text_returns_empty(self):
        assert _extract_keywords("") == []

    def test_mixed_language(self):
        keywords = _extract_keywords("Redis 是缓存系统")
        assert "redis" in keywords
        assert any(len(k) == 2 and k not in ("re",) for k in keywords if not k.isascii())


# ── find_evidence_keyword ──


class TestFindEvidenceKeyword:
    def test_finds_matching_source(self):
        fact = AtomicFact(text="Event sourcing stores state changes as a sequence of events")
        sources = {
            "note-a.md": "Event sourcing is a pattern that stores state changes as events.",
            "note-b.md": "This document is about unrelated topics like gardening.",
        }
        evidence = find_evidence_keyword(fact, sources)
        assert len(evidence) == 1
        assert evidence[0].source_note == "note-a.md"
        assert evidence[0].matched_by == "keyword"

    def test_no_keywords_returns_empty(self):
        fact = AtomicFact(text="")
        evidence = find_evidence_keyword(fact, {"note.md": "some content"})
        assert evidence == []

    def test_no_matching_source_returns_empty(self):
        fact = AtomicFact(text="Quantum computing uses superposition and entanglement")
        sources = {"note.md": "This is about baking bread and pastries."}
        evidence = find_evidence_keyword(fact, sources)
        assert evidence == []

    def test_excerpt_truncated_to_500_chars(self):
        long_para = "distributed cache system " * 40  # > 500 chars
        fact = AtomicFact(text="distributed cache system")
        evidence = find_evidence_keyword(fact, {"note.md": long_para})
        assert len(evidence) == 1
        assert len(evidence[0].excerpt) <= 500

    def test_picks_best_matching_paragraph(self):
        fact = AtomicFact(text="distributed cache system replication")
        content = (
            "First paragraph about distributed systems only.\n\n"
            "Second paragraph about distributed cache system replication in detail."
        )
        evidence = find_evidence_keyword(fact, {"note.md": content})
        assert len(evidence) == 1
        assert "replication in detail" in evidence[0].excerpt


# ── compute_fidelity_score ──


class TestComputeFidelityScore:
    def test_all_supported_scores_100(self):
        report = VerifyReport(supported=5, unsupported=0, unverifiable=0, total_facts=5)
        assert compute_fidelity_score(report) == 100

    def test_all_unsupported_scores_0(self):
        report = VerifyReport(supported=0, unsupported=5, unverifiable=0, total_facts=5)
        assert compute_fidelity_score(report) == 0

    def test_unverifiable_counts_half(self):
        report = VerifyReport(supported=0, unsupported=0, unverifiable=4, total_facts=4)
        assert compute_fidelity_score(report) == 50

    def test_mixed_verdicts(self):
        # 2 supported + 0.5*2 unverifiable = 3 / 4 total = 75
        report = VerifyReport(supported=2, unsupported=0, unverifiable=2, total_facts=4)
        assert compute_fidelity_score(report) == 75

    def test_zero_total_facts_scores_100(self):
        report = VerifyReport(supported=0, unsupported=0, unverifiable=0, total_facts=0)
        assert compute_fidelity_score(report) == 100

    def test_score_clamped_to_valid_range(self):
        report = VerifyReport(supported=3, unsupported=1, unverifiable=0, total_facts=4)
        score = compute_fidelity_score(report)
        assert 0 <= score <= 100


# ── VerifyCache ──


class TestVerifyCache:
    def test_needs_verify_true_for_unknown_file(self, tmp_path: Path):
        concept = tmp_path / "concept.md"
        concept.write_text("content", encoding="utf-8")
        cache = VerifyCache(tmp_path / "cache.json")
        assert cache.needs_verify(concept) is True

    def test_needs_verify_false_after_mark(self, tmp_path: Path):
        concept = tmp_path / "concept.md"
        concept.write_text("content", encoding="utf-8")
        cache = VerifyCache(tmp_path / "cache.json")
        cache.mark_verified(concept)
        assert cache.needs_verify(concept) is False

    def test_needs_verify_true_after_content_changes(self, tmp_path: Path):
        concept = tmp_path / "concept.md"
        concept.write_text("content v1", encoding="utf-8")
        cache = VerifyCache(tmp_path / "cache.json")
        cache.mark_verified(concept)

        concept.write_text("content v2", encoding="utf-8")
        assert cache.needs_verify(concept) is True

    def test_needs_verify_true_for_missing_file(self, tmp_path: Path):
        concept = tmp_path / "missing.md"
        cache = VerifyCache(tmp_path / "cache.json")
        assert cache.needs_verify(concept) is True

    def test_save_and_reload_persists_hashes(self, tmp_path: Path):
        concept = tmp_path / "concept.md"
        concept.write_text("content", encoding="utf-8")
        cache_path = tmp_path / "cache.json"

        cache = VerifyCache(cache_path)
        cache.mark_verified(concept)
        cache.save()

        assert cache_path.exists()
        saved = json.loads(cache_path.read_text(encoding="utf-8"))
        assert str(concept) in saved

        reloaded = VerifyCache(cache_path)
        assert reloaded.needs_verify(concept) is False

    def test_load_handles_corrupt_cache_file(self, tmp_path: Path):
        cache_path = tmp_path / "cache.json"
        cache_path.write_text("not valid json", encoding="utf-8")
        cache = VerifyCache(cache_path)
        assert cache._data == {}


# ── decompose_atomic_facts ──


class TestDecomposeAtomicFacts:
    @pytest.mark.asyncio
    async def test_empty_body_returns_empty_without_calling_llm(self):
        provider = AsyncMock()
        facts = await decompose_atomic_facts("   ", "Concept", provider)
        assert facts == []
        provider.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_parses_json_array_response(self):
        provider = AsyncMock()
        provider.chat.return_value = json.dumps([
            {"fact": "X stores events", "section": "Definition"},
            {"fact": "X supports replay"},
        ])
        facts = await decompose_atomic_facts("Body text", "X", provider)
        assert len(facts) == 2
        assert facts[0].text == "X stores events"
        assert facts[0].section == "Definition"
        assert facts[0].concept == "X"
        assert facts[1].section == ""

    @pytest.mark.asyncio
    async def test_strips_markdown_json_fences(self):
        provider = AsyncMock()
        provider.chat.return_value = '```json\n[{"fact": "A fact"}]\n```'
        facts = await decompose_atomic_facts("Body", "X", provider)
        assert len(facts) == 1
        assert facts[0].text == "A fact"

    @pytest.mark.asyncio
    async def test_malformed_json_returns_empty(self):
        provider = AsyncMock()
        provider.chat.return_value = "not json at all"
        facts = await decompose_atomic_facts("Body", "X", provider)
        assert facts == []

    @pytest.mark.asyncio
    async def test_caps_at_eight_facts(self):
        provider = AsyncMock()
        provider.chat.return_value = json.dumps(
            [{"fact": f"Fact {i}"} for i in range(12)]
        )
        facts = await decompose_atomic_facts("Body", "X", provider)
        assert len(facts) == 8


# ── assign_verdicts ──


class TestAssignVerdicts:
    @pytest.mark.asyncio
    async def test_empty_pairs_returns_empty_without_calling_llm(self):
        provider = AsyncMock()
        checks = await assign_verdicts([], provider)
        assert checks == []
        provider.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_maps_verdicts_by_index(self):
        provider = AsyncMock()
        provider.chat.return_value = json.dumps([
            {"index": 0, "verdict": "supported", "explanation": "matches source"},
            {"index": 1, "verdict": "unsupported", "explanation": "contradicts source"},
        ])
        fact_a = AtomicFact(text="A")
        fact_b = AtomicFact(text="B")
        pairs = [(fact_a, []), (fact_b, [])]

        checks = await assign_verdicts(pairs, provider)
        assert checks[0].verdict == FactVerdict.SUPPORTED
        assert checks[0].explanation == "matches source"
        assert checks[1].verdict == FactVerdict.UNSUPPORTED

    @pytest.mark.asyncio
    async def test_missing_llm_verdict_defaults_unverifiable(self):
        provider = AsyncMock()
        provider.chat.return_value = json.dumps([])
        fact = AtomicFact(text="A")
        checks = await assign_verdicts([(fact, [])], provider)
        assert checks[0].verdict == FactVerdict.UNVERIFIABLE
        assert "did not return a verdict" in checks[0].explanation

    @pytest.mark.asyncio
    async def test_evidence_is_preserved_on_check(self):
        provider = AsyncMock()
        provider.chat.return_value = json.dumps([{"index": 0, "verdict": "supported"}])
        fact = AtomicFact(text="A")
        ev = Evidence(source_note="note.md", excerpt="text")
        checks = await assign_verdicts([(fact, [ev])], provider)
        assert checks[0].evidence == [ev]


# ── verify_concept ──


class TestVerifyConcept:
    @pytest.mark.asyncio
    async def test_shallow_mode_supported_when_name_in_sources(self):
        entry = ConceptEntry(name="caching")
        content = "# caching\n\nCaching stores data for reuse."
        sources = {"note.md": "This note explains caching in depth."}

        result = await verify_concept(entry, content, sources, provider=None, depth="shallow")
        assert result.supported_count == 1
        assert result.unverifiable_count == 0

    @pytest.mark.asyncio
    async def test_shallow_mode_unverifiable_when_name_absent(self):
        entry = ConceptEntry(name="caching")
        content = "# caching\n\nCaching stores data for reuse."
        sources = {"note.md": "This note is about something unrelated."}

        result = await verify_concept(entry, content, sources, provider=None, depth="shallow")
        assert result.supported_count == 0
        assert result.unverifiable_count == 1

    @pytest.mark.asyncio
    async def test_empty_body_returns_empty_result(self):
        entry = ConceptEntry(name="X")
        result = await verify_concept(entry, "", {}, provider=None, depth="shallow")
        assert result.total_facts == 0

    @pytest.mark.asyncio
    async def test_standard_mode_requires_provider(self):
        entry = ConceptEntry(name="X")
        content = "# X\n\nSome body content here."
        with pytest.raises(AssertionError):
            await verify_concept(entry, content, {}, provider=None, depth="standard")

    @pytest.mark.asyncio
    async def test_standard_mode_aggregates_verdict_counts(self):
        provider = AsyncMock()
        provider.chat.side_effect = [
            json.dumps([{"fact": "X does A"}, {"fact": "X does B"}]),
            json.dumps([
                {"index": 0, "verdict": "supported"},
                {"index": 1, "verdict": "unsupported"},
            ]),
        ]
        entry = ConceptEntry(name="X")
        content = "# X\n\nX does A and X does B."
        sources = {"note.md": "X does A and X does B according to this source."}

        result = await verify_concept(entry, content, sources, provider, depth="standard")
        assert result.supported_count == 1
        assert result.unsupported_count == 1
        assert result.total_facts == 2

    @pytest.mark.asyncio
    async def test_standard_mode_no_facts_returns_empty_result(self):
        provider = AsyncMock()
        provider.chat.return_value = json.dumps([])
        entry = ConceptEntry(name="X")
        content = "# X\n\nSome body."
        result = await verify_concept(entry, content, {}, provider, depth="standard")
        assert result.total_facts == 0


# ── update_concept_confidence ──


class TestUpdateConceptConfidence:
    def _write_concept(self, path: Path, confidence: float) -> None:
        path.write_text(
            f"---\nname: X\nconfidence: {confidence}\n---\n# X\n\nBody.",
            encoding="utf-8",
        )

    def test_no_change_when_zero_facts(self, tmp_path: Path):
        concept = tmp_path / "x.md"
        self._write_concept(concept, 0.5)
        verification = ConceptVerification(concept_name="X")
        update_concept_confidence(concept, verification)
        assert "confidence: 0.5" in concept.read_text(encoding="utf-8")

    def test_no_change_when_ratio_high(self, tmp_path: Path):
        concept = tmp_path / "x.md"
        self._write_concept(concept, 0.5)
        verification = ConceptVerification(
            concept_name="X",
            fact_checks=[
                FactCheck(fact=AtomicFact(text="a"), verdict=FactVerdict.SUPPORTED),
                FactCheck(fact=AtomicFact(text="b"), verdict=FactVerdict.SUPPORTED),
            ],
            supported_count=2,
        )
        update_concept_confidence(concept, verification)
        assert "confidence: 0.5" in concept.read_text(encoding="utf-8")

    def test_moderate_penalty_when_ratio_between_half_and_08(self, tmp_path: Path):
        concept = tmp_path / "x.md"
        self._write_concept(concept, 0.5)
        # ratio = 0.6 (>=0.5, <0.8) -> penalty 0.9
        verification = ConceptVerification(
            concept_name="X",
            fact_checks=[
                FactCheck(fact=AtomicFact(text="a"), verdict=FactVerdict.SUPPORTED),
                FactCheck(fact=AtomicFact(text="b"), verdict=FactVerdict.SUPPORTED),
                FactCheck(fact=AtomicFact(text="c"), verdict=FactVerdict.SUPPORTED),
                FactCheck(fact=AtomicFact(text="d"), verdict=FactVerdict.SUPPORTED),
                FactCheck(fact=AtomicFact(text="e"), verdict=FactVerdict.SUPPORTED),
                FactCheck(fact=AtomicFact(text="f"), verdict=FactVerdict.UNSUPPORTED),
                FactCheck(fact=AtomicFact(text="g"), verdict=FactVerdict.UNSUPPORTED),
                FactCheck(fact=AtomicFact(text="h"), verdict=FactVerdict.UNSUPPORTED),
                FactCheck(fact=AtomicFact(text="i"), verdict=FactVerdict.UNSUPPORTED),
            ],
            supported_count=5,
            unsupported_count=4,
        )
        assert verification.supported_ratio == pytest.approx(5 / 9)
        update_concept_confidence(concept, verification)
        content = concept.read_text(encoding="utf-8")
        assert "confidence: 0.45" in content

    def test_heavy_penalty_when_ratio_below_half(self, tmp_path: Path):
        concept = tmp_path / "x.md"
        self._write_concept(concept, 0.5)
        verification = ConceptVerification(
            concept_name="X",
            fact_checks=[
                FactCheck(fact=AtomicFact(text="a"), verdict=FactVerdict.UNSUPPORTED),
                FactCheck(fact=AtomicFact(text="b"), verdict=FactVerdict.SUPPORTED),
            ],
            supported_count=1,
            unsupported_count=1,
        )
        update_concept_confidence(concept, verification)
        content = concept.read_text(encoding="utf-8")
        # penalty 0.8 -> 0.5 * 0.8 = 0.4
        assert "confidence: 0.4" in content

    def test_confidence_floor_at_point_one(self, tmp_path: Path):
        concept = tmp_path / "x.md"
        self._write_concept(concept, 0.1)
        verification = ConceptVerification(
            concept_name="X",
            fact_checks=[
                FactCheck(fact=AtomicFact(text="a"), verdict=FactVerdict.UNSUPPORTED),
            ],
            unsupported_count=1,
        )
        update_concept_confidence(concept, verification)
        content = concept.read_text(encoding="utf-8")
        assert "confidence: 0.1" in content

    def test_missing_confidence_field_no_op(self, tmp_path: Path):
        concept = tmp_path / "x.md"
        concept.write_text("---\nname: X\n---\n# X\n\nBody.", encoding="utf-8")
        verification = ConceptVerification(
            concept_name="X",
            fact_checks=[
                FactCheck(fact=AtomicFact(text="a"), verdict=FactVerdict.UNSUPPORTED),
            ],
            unsupported_count=1,
        )
        # Should not raise even though there's no confidence field to update.
        update_concept_confidence(concept, verification)
