"""Tests for knowledge confidence decay and complexity scoring."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from neocortex.decay import (
    MAX_CONFIDENCE,
    boost_confidence,
    decayed_confidence,
    knowledge_complexity,
    months_between,
)
from neocortex.models import ConceptEntry


# ── months_between ──


class TestMonthsBetween:
    def test_same_day(self):
        assert months_between("2026-04-01", "2026-04-01") == 0.0

    def test_one_month(self):
        result = months_between("2026-03-01", "2026-03-31")
        assert 0.9 < result < 1.1

    def test_across_year(self):
        result = months_between("2025-06-15", "2026-06-15")
        assert 11.5 < result < 12.5

    def test_empty_date_a(self):
        assert months_between("", "2026-04-01") == 0.0

    def test_none_date_a(self):
        assert months_between(None, "2026-04-01") == 0.0

    def test_invalid_date(self):
        assert months_between("not-a-date", "2026-04-01") == 0.0

    def test_negative_when_b_before_a(self):
        result = months_between("2026-06-01", "2026-04-01")
        assert result < 0


# ── decayed_confidence ──


class TestDecayedConfidence:
    def test_no_decay_today(self):
        today = date.today().isoformat()
        assert decayed_confidence(0.8, today) == 0.8

    def test_one_month_decay(self):
        one_month_ago = (date.today() - timedelta(days=30)).isoformat()
        result = decayed_confidence(1.0, one_month_ago)
        assert 0.93 < result < 0.96

    def test_six_months_decay(self):
        six_months_ago = (date.today() - timedelta(days=183)).isoformat()
        result = decayed_confidence(1.0, six_months_ago)
        assert 0.65 < result < 0.75

    def test_twelve_months_approximately_50_percent(self):
        twelve_months_ago = (date.today() - timedelta(days=365)).isoformat()
        result = decayed_confidence(1.0, twelve_months_ago)
        assert 0.45 < result < 0.55

    def test_empty_last_updated(self):
        assert decayed_confidence(0.8, "") == 0.8

    def test_future_date_no_decay(self):
        future = (date.today() + timedelta(days=30)).isoformat()
        assert decayed_confidence(0.8, future) == 0.8

    def test_never_goes_below_zero(self):
        very_old = (date.today() - timedelta(days=3650)).isoformat()
        result = decayed_confidence(0.5, very_old)
        assert result >= 0.0


# ── boost_confidence ──


class TestBoostConfidence:
    def test_normal_boost(self):
        assert boost_confidence(0.5, 0.1) == pytest.approx(0.6)

    def test_capped_at_max(self):
        assert boost_confidence(0.95, 0.1) == MAX_CONFIDENCE

    def test_already_at_max(self):
        assert boost_confidence(1.0, 0.1) == MAX_CONFIDENCE

    def test_zero_boost(self):
        assert boost_confidence(0.5, 0.0) == pytest.approx(0.5)


# ── knowledge_complexity ──


class TestKnowledgeComplexity:
    def test_empty_concepts(self):
        result = knowledge_complexity([])
        assert result["score"] == 0.0
        assert result["concept_count"] == 0
        assert result["avg_depth"] == 0.0
        assert result["connectivity"] == 0.0
        assert result["decaying"] == []

    def test_single_concept(self):
        today = date.today().isoformat()
        concepts = [
            ConceptEntry(
                name="Redis",
                confidence=0.8,
                last_updated=today,
                related_concepts=[],
            ),
        ]
        result = knowledge_complexity(concepts)
        assert result["concept_count"] == 1
        assert result["avg_depth"] == pytest.approx(0.8, abs=0.01)
        assert result["connectivity"] == 0.0

    def test_connected_concepts(self):
        today = date.today().isoformat()
        concepts = [
            ConceptEntry(
                name="Event Sourcing",
                confidence=0.9,
                last_updated=today,
                related_concepts=["CQRS"],
            ),
            ConceptEntry(
                name="CQRS",
                confidence=0.7,
                last_updated=today,
                related_concepts=["Event Sourcing"],
            ),
        ]
        result = knowledge_complexity(concepts)
        assert result["concept_count"] == 2
        assert result["connectivity"] > 0
        assert result["score"] > 0

    def test_decaying_concepts_listed(self):
        old_date = (date.today() - timedelta(days=365)).isoformat()
        concepts = [
            ConceptEntry(
                name="Forgotten",
                confidence=0.4,
                last_updated=old_date,
                related_concepts=[],
            ),
        ]
        result = knowledge_complexity(concepts)
        assert "Forgotten" in result["decaying"]

    def test_fresh_concept_not_decaying(self):
        today = date.today().isoformat()
        concepts = [
            ConceptEntry(
                name="Fresh",
                confidence=0.8,
                last_updated=today,
                related_concepts=[],
            ),
        ]
        result = knowledge_complexity(concepts)
        assert result["decaying"] == []


# ── check_decaying_concepts (linter integration) ──


@pytest.fixture()
def notes_dir(tmp_path):
    d = tmp_path / "notes"
    d.mkdir()
    return d


class TestCheckDecayingConcepts:
    def test_detects_decayed_concept(self, notes_dir):
        from neocortex.linter import check_decaying_concepts

        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        old_date = (date.today() - timedelta(days=400)).isoformat()
        (concepts_dir / "stale-skill.md").write_text(
            f"---\nname: Stale Skill\nconfidence: 0.4\nlast_updated: {old_date}\nsource_notes: []\n---\n# Stale Skill",
            encoding="utf-8",
        )
        issues = check_decaying_concepts(notes_dir)
        assert len(issues) == 1
        assert issues[0].type == "decaying"
        assert issues[0].severity == "warning"
        assert "Stale Skill" in issues[0].message

    def test_no_decay_recent_concept(self, notes_dir):
        from neocortex.linter import check_decaying_concepts

        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        today = date.today().isoformat()
        (concepts_dir / "fresh.md").write_text(
            f"---\nname: Fresh\nconfidence: 0.8\nlast_updated: {today}\nsource_notes: []\n---\n# Fresh",
            encoding="utf-8",
        )
        issues = check_decaying_concepts(notes_dir)
        assert len(issues) == 0

    def test_empty_concepts_dir(self, notes_dir):
        from neocortex.linter import check_decaying_concepts

        issues = check_decaying_concepts(notes_dir)
        assert len(issues) == 0

    def test_concept_without_last_updated(self, notes_dir):
        from neocortex.linter import check_decaying_concepts

        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "no-date.md").write_text(
            "---\nname: No Date\nconfidence: 0.1\nsource_notes: []\n---\n# No Date",
            encoding="utf-8",
        )
        issues = check_decaying_concepts(notes_dir)
        assert len(issues) == 0
