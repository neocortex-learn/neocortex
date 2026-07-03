"""Tests for the research engine."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.models import Profile, Skills, DomainSkill, SkillLevel
from neocortex.researcher import (
    SearchResult,
    analyze_gaps_for_query,
    rank_results,
    web_search,
    _get_existing_concepts,
)


# ── web_search ──


class TestWebSearch:
    def test_returns_results(self):
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        mock_ddgs_instance.text.return_value = [
            {"title": "Article A", "href": "https://a.com", "body": "About A"},
            {"title": "Article B", "href": "https://b.com", "body": "About B"},
        ]

        with patch("ddgs.DDGS", return_value=mock_ddgs_instance):
            results = web_search("test query", max_results=5)

        assert len(results) == 2
        assert results[0].title == "Article A"
        assert results[0].url == "https://a.com"
        assert results[1].snippet == "About B"

    def test_returns_empty_on_exception(self):
        with patch("ddgs.DDGS", side_effect=Exception("fail")):
            results = web_search("test query")

        assert results == []

    def test_respects_max_results(self):
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        mock_ddgs_instance.text.return_value = [
            {"title": f"Article {i}", "href": f"https://{i}.com", "body": f"About {i}"}
            for i in range(10)
        ]

        with patch("ddgs.DDGS", return_value=mock_ddgs_instance):
            web_search("test", max_results=3)

        mock_ddgs_instance.text.assert_called_once_with("test", max_results=3)


# ── analyze_gaps_for_query ──


class TestAnalyzeGaps:
    @pytest.fixture
    def profile(self):
        return Profile(
            skills=Skills(
                domains={
                    "backend": DomainSkill(
                        level=SkillLevel.PROFICIENT,
                        gaps=["event sourcing", "cqrs"],
                    ),
                },
            ),
        )

    @pytest.mark.asyncio
    async def test_returns_queries_from_llm(self, profile):
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=json.dumps([
            "event sourcing snapshots",
            "CQRS read model rebuild",
            "event store implementation",
        ]))

        with patch("neocortex.researcher._get_existing_concepts", return_value=["Domain Events"]):
            queries = await analyze_gaps_for_query("Event Sourcing", profile, provider)

        assert len(queries) == 3
        assert "event sourcing snapshots" in queries

    @pytest.mark.asyncio
    async def test_falls_back_to_topic_on_failure(self, profile):
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value="not json")

        queries = await analyze_gaps_for_query("Event Sourcing", profile, provider)

        assert queries == ["Event Sourcing"]

    @pytest.mark.asyncio
    async def test_limits_to_5_queries(self, profile):
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=json.dumps([f"q{i}" for i in range(10)]))

        queries = await analyze_gaps_for_query("topic", profile, provider)

        assert len(queries) <= 5


# ── rank_results ──


class TestRankResults:
    @pytest.fixture
    def results(self):
        return [
            SearchResult("Article A", "https://a.com", "About event sourcing"),
            SearchResult("Article B", "https://b.com", "About cooking"),
            SearchResult("Article C", "https://c.com", "About CQRS patterns"),
        ]

    @pytest.fixture
    def profile(self):
        return Profile(
            skills=Skills(
                domains={
                    "backend": DomainSkill(
                        level=SkillLevel.PROFICIENT,
                        gaps=["event sourcing"],
                    ),
                },
            ),
        )

    @pytest.mark.asyncio
    async def test_returns_ranked_results(self, results, profile):
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value="[0, 2]")

        ranked = await rank_results(results, "Event Sourcing", profile, provider, max_results=3)

        assert len(ranked) == 2
        assert ranked[0].url == "https://a.com"
        assert ranked[1].url == "https://c.com"

    @pytest.mark.asyncio
    async def test_falls_back_on_bad_json(self, results, profile):
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value="not json")

        ranked = await rank_results(results, "topic", profile, provider, max_results=2)

        assert len(ranked) == 2

    @pytest.mark.asyncio
    async def test_empty_results(self, profile):
        provider = AsyncMock()
        ranked = await rank_results([], "topic", profile, provider)
        assert ranked == []

    @pytest.mark.asyncio
    async def test_out_of_range_indices_ignored(self, results, profile):
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value="[0, 99, -1]")

        ranked = await rank_results(results, "topic", profile, provider, max_results=5)

        assert len(ranked) == 1
        assert ranked[0].url == "https://a.com"


# ── _get_existing_concepts ──


class TestGetExistingConcepts:
    def test_returns_empty_on_missing_dir(self, tmp_path):
        with patch("neocortex.config.get_notes_dir", return_value=tmp_path):
            concepts = _get_existing_concepts()
        assert concepts == []

    def test_returns_concept_names(self, tmp_path):
        concepts_dir = tmp_path / "concepts"
        concepts_dir.mkdir()
        (concepts_dir / "event-sourcing.md").write_text(
            "---\ntype: concept\nname: Event Sourcing\nevidence_count: 3\nsource_notes: []\n---\n# Event Sourcing\n"
        )
        (concepts_dir / "cqrs.md").write_text(
            "---\ntype: concept\nname: CQRS\nevidence_count: 1\nsource_notes: []\n---\n# CQRS\n"
        )

        with patch("neocortex.config.get_notes_dir", return_value=tmp_path):
            concepts = _get_existing_concepts()

        assert len(concepts) == 2
