"""Tests for the knowledge base health check engine."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from neocortex.linter import (
    check_broken_links,
    check_coverage_gaps,
    check_duplicate_concepts,
    check_orphan_notes,
    check_stale_concepts,
    fix_broken_links,
    lint_knowledge_base,
)
from neocortex.models import (
    DomainSkill,
    IntegrationSkill,
    LintReport,
    Profile,
    SkillLevel,
    Skills,
)


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
                "backend": DomainSkill(
                    level=SkillLevel.PROFICIENT,
                    gaps=["streaming-ssr", "event-sourcing"],
                ),
            },
            integrations={
                "aws": IntegrationSkill(
                    level=SkillLevel.BEGINNER,
                    gaps=["lambda-cold-start"],
                ),
            },
        )
    )


class TestOrphanNotes:
    def test_detects_orphan(self, notes_dir):
        (notes_dir / "lonely.md").write_text("No links here.", encoding="utf-8")
        issues = check_orphan_notes(notes_dir)
        assert len(issues) == 1
        assert issues[0].type == "orphan"
        assert issues[0].severity == "warning"
        assert issues[0].auto_fixable is True
        assert "lonely.md" in issues[0].message

    def test_note_with_outgoing_link_is_not_orphan(self, notes_dir):
        (notes_dir / "linked.md").write_text(
            "Check out [[some-concept]] for more.", encoding="utf-8",
        )
        issues = check_orphan_notes(notes_dir)
        assert len(issues) == 0

    def test_note_referenced_by_concept_is_not_orphan(self, notes_dir):
        (notes_dir / "referenced.md").write_text("Plain content.", encoding="utf-8")
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "test-concept.md").write_text(
            "---\nname: Test\nsource_notes: [referenced.md]\n---\n# Test",
            encoding="utf-8",
        )
        issues = check_orphan_notes(notes_dir)
        assert len(issues) == 0

    def test_note_referenced_by_wikilink_is_not_orphan(self, notes_dir):
        (notes_dir / "target.md").write_text("Plain content.", encoding="utf-8")
        (notes_dir / "linker.md").write_text("See [[target]] for details.", encoding="utf-8")
        issues = check_orphan_notes(notes_dir)
        linker_issues = [i for i in issues if "linker.md" in i.message]
        target_issues = [i for i in issues if "target.md" in i.message]
        assert len(target_issues) == 0
        assert len(linker_issues) == 0

    def test_empty_dir(self, notes_dir):
        issues = check_orphan_notes(notes_dir)
        assert len(issues) == 0


class TestBrokenLinks:
    def test_detects_broken_link(self, notes_dir):
        (notes_dir / "note.md").write_text(
            "See [[nonexistent-concept]] for info.", encoding="utf-8",
        )
        issues = check_broken_links(notes_dir)
        assert len(issues) == 1
        assert issues[0].type == "broken_link"
        assert "nonexistent-concept" in issues[0].message
        assert issues[0].auto_fixable is True

    def test_valid_link_to_note(self, notes_dir):
        (notes_dir / "target.md").write_text("I exist.", encoding="utf-8")
        (notes_dir / "source.md").write_text("Link to [[target]].", encoding="utf-8")
        issues = check_broken_links(notes_dir)
        assert len(issues) == 0

    def test_valid_link_to_concept(self, notes_dir):
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "redis.md").write_text(
            "---\nname: Redis\n---\n# Redis", encoding="utf-8",
        )
        (notes_dir / "note.md").write_text("Use [[redis]] caching.", encoding="utf-8")
        issues = check_broken_links(notes_dir)
        assert len(issues) == 0

    def test_link_with_display_text(self, notes_dir):
        (notes_dir / "event-sourcing.md").write_text("Content.", encoding="utf-8")
        (notes_dir / "note.md").write_text(
            "Learn about [[event-sourcing|Event Sourcing]] pattern.", encoding="utf-8",
        )
        issues = check_broken_links(notes_dir)
        assert len(issues) == 0

    def test_broken_link_in_concept_file(self, notes_dir):
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "cqrs.md").write_text(
            "Related: [[event-sourcing-intro]]", encoding="utf-8",
        )
        issues = check_broken_links(notes_dir)
        assert len(issues) == 1
        assert "event-sourcing-intro" in issues[0].message

    def test_empty_dir(self, notes_dir):
        issues = check_broken_links(notes_dir)
        assert len(issues) == 0


class TestStaleConcepts:
    def test_detects_stale_reference(self, notes_dir):
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "redis.md").write_text(
            "---\nname: Redis\nsource_notes: [deleted-note.md]\n---\n# Redis",
            encoding="utf-8",
        )
        issues = check_stale_concepts(notes_dir)
        assert len(issues) == 1
        assert issues[0].type == "stale"
        assert "deleted-note.md" in issues[0].message

    def test_valid_source_note(self, notes_dir):
        (notes_dir / "existing.md").write_text("Content.", encoding="utf-8")
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "redis.md").write_text(
            "---\nname: Redis\nsource_notes: [existing.md]\n---\n# Redis",
            encoding="utf-8",
        )
        issues = check_stale_concepts(notes_dir)
        assert len(issues) == 0

    def test_no_concepts_dir(self, notes_dir):
        issues = check_stale_concepts(notes_dir)
        assert len(issues) == 0

    def test_concept_with_empty_source_notes(self, notes_dir):
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "empty.md").write_text(
            "---\nname: Empty\nsource_notes: []\n---\n# Empty",
            encoding="utf-8",
        )
        issues = check_stale_concepts(notes_dir)
        assert len(issues) == 0


class TestCoverageGaps:
    def test_detects_uncovered_gap(self, notes_dir, profile):
        issues = check_coverage_gaps(notes_dir, profile)
        assert len(issues) == 3
        gap_names = {i.message for i in issues}
        assert any("streaming-ssr" in m for m in gap_names)
        assert any("event-sourcing" in m for m in gap_names)
        assert any("lambda-cold-start" in m for m in gap_names)
        for issue in issues:
            assert issue.type == "coverage_gap"
            assert issue.severity == "info"

    def test_gap_covered_by_concept(self, notes_dir, profile):
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "streaming-ssr.md").write_text(
            "---\nname: Streaming SSR\n---\n# Streaming SSR", encoding="utf-8",
        )
        (concepts_dir / "event-sourcing.md").write_text(
            "---\nname: Event Sourcing\n---\n# Event Sourcing", encoding="utf-8",
        )
        (concepts_dir / "lambda-cold-start.md").write_text(
            "---\nname: Lambda Cold Start\n---\n# Lambda Cold Start", encoding="utf-8",
        )
        issues = check_coverage_gaps(notes_dir, profile)
        assert len(issues) == 0

    def test_no_gaps_in_profile(self, notes_dir):
        empty_profile = Profile()
        issues = check_coverage_gaps(notes_dir, empty_profile)
        assert len(issues) == 0


class TestDuplicateConcepts:
    def test_detects_duplicates(self, notes_dir):
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "event-sourcing.md").write_text(
            "---\nname: Event Sourcing\n---\n# Event Sourcing", encoding="utf-8",
        )
        (concepts_dir / "event_sourcing.md").write_text(
            "---\nname: Event Sourcing\n---\n# Event Sourcing", encoding="utf-8",
        )
        issues = check_duplicate_concepts(notes_dir)
        assert len(issues) == 1
        assert issues[0].type == "duplicate"
        assert issues[0].auto_fixable is True

    def test_no_duplicates(self, notes_dir):
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "redis.md").write_text(
            "---\nname: Redis\n---\n# Redis", encoding="utf-8",
        )
        (concepts_dir / "kafka.md").write_text(
            "---\nname: Kafka\n---\n# Kafka", encoding="utf-8",
        )
        issues = check_duplicate_concepts(notes_dir)
        assert len(issues) == 0

    def test_no_concepts_dir(self, notes_dir):
        issues = check_duplicate_concepts(notes_dir)
        assert len(issues) == 0


class TestFixBrokenLinks:
    def test_removes_broken_wikilinks(self, notes_dir):
        (notes_dir / "note.md").write_text(
            "See [[missing]] and [[also-missing|display text]] for info.",
            encoding="utf-8",
        )
        fixed = fix_broken_links(notes_dir)
        assert fixed == 2
        content = (notes_dir / "note.md").read_text(encoding="utf-8")
        assert "[[missing]]" not in content
        assert "[[also-missing" not in content
        assert "missing" in content
        assert "display text" in content

    def test_preserves_valid_links(self, notes_dir):
        (notes_dir / "target.md").write_text("I exist.", encoding="utf-8")
        (notes_dir / "note.md").write_text(
            "Link to [[target]] and [[broken-one]].", encoding="utf-8",
        )
        fixed = fix_broken_links(notes_dir)
        assert fixed == 1
        content = (notes_dir / "note.md").read_text(encoding="utf-8")
        assert "[[target]]" in content
        assert "[[broken-one]]" not in content

    def test_no_changes_when_all_valid(self, notes_dir):
        (notes_dir / "a.md").write_text("Link to [[b]].", encoding="utf-8")
        (notes_dir / "b.md").write_text("Link to [[a]].", encoding="utf-8")
        fixed = fix_broken_links(notes_dir)
        assert fixed == 0

    def test_empty_dir(self, notes_dir):
        fixed = fix_broken_links(notes_dir)
        assert fixed == 0


class TestLintReport:
    def test_score_calculation(self):
        report = LintReport()
        assert report.score == 100

    def test_score_from_issues(self):
        from neocortex.models import LintIssue
        report = LintReport(
            issues=[
                LintIssue(type="broken_link", severity="error", message="err"),
                LintIssue(type="orphan", severity="warning", message="warn"),
                LintIssue(type="coverage_gap", severity="info", message="info"),
            ],
        )
        assert len(report.issues) == 3

    def test_stats_dict(self):
        report = LintReport(
            stats={"orphan": 2, "broken_link": 1},
        )
        assert report.stats["orphan"] == 2
        assert report.stats["broken_link"] == 1


class TestLintKnowledgeBase:
    @pytest.mark.asyncio
    async def test_full_lint_no_provider(self, notes_dir, profile):
        (notes_dir / "orphan.md").write_text("No links.", encoding="utf-8")
        (notes_dir / "linked.md").write_text("See [[missing-target]].", encoding="utf-8")

        report = await lint_knowledge_base(notes_dir, profile)

        assert report.score < 100
        assert report.stats["orphan"] >= 1
        assert report.stats["broken_link"] >= 1
        assert report.stats["suggestion"] == 0

    @pytest.mark.asyncio
    async def test_full_lint_empty_kb(self, notes_dir):
        empty_profile = Profile()
        report = await lint_knowledge_base(notes_dir, empty_profile)
        assert report.score == 100
        assert not report.issues

    @pytest.mark.asyncio
    async def test_full_lint_with_provider(self, notes_dir, profile):
        concepts_dir = notes_dir / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "redis.md").write_text(
            "---\nname: Redis\nsource_notes: []\n---\n# Redis", encoding="utf-8",
        )
        (concepts_dir / "kafka.md").write_text(
            "---\nname: Kafka\nsource_notes: []\n---\n# Kafka", encoding="utf-8",
        )

        mock_provider = AsyncMock()
        mock_provider.chat = AsyncMock(return_value=json.dumps([
            {
                "concept_a": "Redis",
                "concept_b": "Kafka",
                "suggestion": "Explore event-driven caching patterns",
            },
        ]))
        mock_provider.name.return_value = "mock"
        mock_provider.max_context_tokens.return_value = 100000

        from neocortex.llm.base import LLMProvider
        mock_provider.__class__ = type("MockProvider", (LLMProvider,), {
            "chat": mock_provider.chat,
            "describe_image": AsyncMock(),
            "max_context_tokens": lambda self: 100000,
            "name": lambda self: "mock",
        })

        report = await lint_knowledge_base(notes_dir, profile, provider=mock_provider)
        assert report.stats.get("suggestion", 0) >= 1

    @pytest.mark.asyncio
    async def test_score_decreases_with_issues(self, notes_dir, profile):
        for i in range(5):
            (notes_dir / f"orphan-{i}.md").write_text("No links.", encoding="utf-8")

        report = await lint_knowledge_base(notes_dir, profile)
        assert report.score < 100
        expected_max = 100 - (5 * 5) - (3 * 1)
        assert report.score <= expected_max
