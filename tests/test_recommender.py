from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from neocortex.models import (
    Calibration,
    Language,
    Persona,
    Profile,
    Recommendation,
)
from neocortex.recommender import _parse_recommendations, generate_recommendations


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


SAMPLE_ITEMS = [
    {
        "topic": "Redis Cluster",
        "reason": "Your profile shows gaps in distributed caching",
        "resources": ["Redis docs", "https://redis.io"],
        "expected_benefit": "Better caching in your API project",
        "priority": "high",
    },
    {
        "topic": "GraphQL",
        "reason": "Complement your REST skills",
        "resources": ["GraphQL spec", "https://graphql.org"],
        "expected_benefit": "Flexible API for frontend team",
        "priority": "medium",
    },
    {
        "topic": "Kubernetes Networking",
        "reason": "You use k8s but lack networking knowledge",
        "resources": ["k8s docs"],
        "expected_benefit": "Debug service mesh issues faster",
        "priority": "low",
    },
]


# ===========================================================================
# 1. _parse_recommendations — pure function tests
# ===========================================================================


class TestParseNormalJsonArray:
    def test_returns_correct_count(self):
        text = json.dumps(SAMPLE_ITEMS)
        results = _parse_recommendations(text, max_count=10)
        assert len(results) == 3

    def test_fields_populated(self):
        text = json.dumps(SAMPLE_ITEMS)
        results = _parse_recommendations(text, max_count=10)
        assert results[0].topic == "Redis Cluster"
        assert results[0].reason == "Your profile shows gaps in distributed caching"
        assert results[0].expected_benefit == "Better caching in your API project"
        assert results[0].priority == "high"
        assert len(results[0].resources) == 2

    def test_all_items_are_recommendation(self):
        text = json.dumps(SAMPLE_ITEMS)
        results = _parse_recommendations(text, max_count=10)
        for r in results:
            assert isinstance(r, Recommendation)


class TestParseMarkdownWrapped:
    def test_json_code_block(self):
        inner = json.dumps(SAMPLE_ITEMS)
        text = f"```json\n{inner}\n```"
        results = _parse_recommendations(text, max_count=10)
        assert len(results) == 3
        assert results[0].topic == "Redis Cluster"

    def test_plain_code_block(self):
        inner = json.dumps(SAMPLE_ITEMS[:1])
        text = f"```\n{inner}\n```"
        results = _parse_recommendations(text, max_count=10)
        assert len(results) == 1


class TestParseDictWithRecommendationsKey:
    def test_recommendations_key(self):
        data = {"recommendations": SAMPLE_ITEMS}
        results = _parse_recommendations(json.dumps(data), max_count=10)
        assert len(results) == 3

    def test_items_key(self):
        data = {"items": SAMPLE_ITEMS[:2]}
        results = _parse_recommendations(json.dumps(data), max_count=10)
        assert len(results) == 2

    def test_topics_key(self):
        data = {"topics": SAMPLE_ITEMS[:1]}
        results = _parse_recommendations(json.dumps(data), max_count=10)
        assert len(results) == 1

    def test_single_object_without_known_key(self):
        data = {"topic": "Docker", "reason": "Need it", "resources": [], "expected_benefit": "", "priority": "high"}
        results = _parse_recommendations(json.dumps(data), max_count=10)
        assert len(results) == 1
        assert results[0].topic == "Docker"


class TestParseResources:
    def test_string_list(self):
        items = [{"topic": "T", "reason": "R", "resources": ["Book A", "URL B"], "expected_benefit": "", "priority": "high"}]
        results = _parse_recommendations(json.dumps(items), max_count=10)
        assert results[0].resources == ["Book A", "URL B"]

    def test_object_list(self):
        items = [{
            "topic": "T",
            "reason": "R",
            "resources": [
                {"title": "Docs", "url": "https://example.com"},
                {"title": "Book", "url": "https://book.com"},
            ],
            "expected_benefit": "",
            "priority": "high",
        }]
        results = _parse_recommendations(json.dumps(items), max_count=10)
        assert len(results[0].resources) == 2
        assert "Docs" in results[0].resources[0]
        assert "https://example.com" in results[0].resources[0]

    def test_mixed_resources(self):
        items = [{
            "topic": "T",
            "reason": "R",
            "resources": [
                "Plain string resource",
                {"title": "With Title", "url": "https://url.com"},
            ],
            "expected_benefit": "",
            "priority": "medium",
        }]
        results = _parse_recommendations(json.dumps(items), max_count=10)
        assert results[0].resources[0] == "Plain string resource"
        assert "With Title" in results[0].resources[1]

    def test_null_resources(self):
        items = [{"topic": "T", "reason": "R", "resources": None, "expected_benefit": "", "priority": "high"}]
        results = _parse_recommendations(json.dumps(items), max_count=10)
        assert results[0].resources == []

    def test_resource_object_title_only(self):
        items = [{"topic": "T", "reason": "R", "resources": [{"title": "Book Only"}], "expected_benefit": "", "priority": "high"}]
        results = _parse_recommendations(json.dumps(items), max_count=10)
        assert results[0].resources == ["Book Only"]

    def test_resource_object_url_only(self):
        items = [{"topic": "T", "reason": "R", "resources": [{"url": "https://only.url"}], "expected_benefit": "", "priority": "high"}]
        results = _parse_recommendations(json.dumps(items), max_count=10)
        assert results[0].resources == ["https://only.url"]


class TestParseInvalidInput:
    def test_invalid_json(self):
        results = _parse_recommendations("this is not json at all", max_count=10)
        assert results == []

    def test_empty_string(self):
        results = _parse_recommendations("", max_count=10)
        assert results == []

    def test_whitespace_only(self):
        results = _parse_recommendations("   \n\t  ", max_count=10)
        assert results == []

    def test_non_list_non_dict(self):
        results = _parse_recommendations('"just a string"', max_count=10)
        assert results == []

    def test_json_with_surrounding_text(self):
        inner = json.dumps(SAMPLE_ITEMS[:1])
        text = f"Here are my recommendations:\n{inner}\nHope this helps!"
        results = _parse_recommendations(text, max_count=10)
        assert len(results) == 1

    def test_items_without_topic_are_skipped(self):
        items = [
            {"topic": "", "reason": "R", "resources": [], "expected_benefit": "", "priority": "high"},
            {"topic": "Valid", "reason": "R", "resources": [], "expected_benefit": "", "priority": "high"},
        ]
        results = _parse_recommendations(json.dumps(items), max_count=10)
        assert len(results) == 1
        assert results[0].topic == "Valid"


class TestParseMaxCount:
    def test_limits_results(self):
        results = _parse_recommendations(json.dumps(SAMPLE_ITEMS), max_count=2)
        assert len(results) == 2

    def test_max_count_greater_than_items(self):
        results = _parse_recommendations(json.dumps(SAMPLE_ITEMS), max_count=100)
        assert len(results) == 3

    def test_max_count_zero(self):
        results = _parse_recommendations(json.dumps(SAMPLE_ITEMS), max_count=0)
        assert results == []


class TestParsePriorityNormalization:
    def test_uppercase_priority_normalized(self):
        items = [{"topic": "T", "reason": "R", "resources": [], "expected_benefit": "", "priority": "HIGH"}]
        results = _parse_recommendations(json.dumps(items), max_count=10)
        assert results[0].priority == "high"

    def test_invalid_priority_defaults_to_medium(self):
        items = [{"topic": "T", "reason": "R", "resources": [], "expected_benefit": "", "priority": "critical"}]
        results = _parse_recommendations(json.dumps(items), max_count=10)
        assert results[0].priority == "medium"

    def test_missing_priority_defaults_to_medium(self):
        items = [{"topic": "T", "reason": "R", "resources": []}]
        results = _parse_recommendations(json.dumps(items), max_count=10)
        assert results[0].priority == "medium"


# ===========================================================================
# 2. generate_recommendations — mock LLM tests
# ===========================================================================


class TestGenerateRecommendations:
    @pytest.mark.asyncio
    async def test_returns_recommendations(self):
        provider = _make_provider_mock(json.dumps(SAMPLE_ITEMS))
        profile = _make_profile()
        results = await generate_recommendations(profile, provider, count=5)
        assert len(results) == 3
        for r in results:
            assert isinstance(r, Recommendation)

    @pytest.mark.asyncio
    async def test_fields_correctly_populated(self):
        provider = _make_provider_mock(json.dumps(SAMPLE_ITEMS[:1]))
        profile = _make_profile()
        results = await generate_recommendations(profile, provider, count=5)
        assert results[0].topic == "Redis Cluster"
        assert results[0].priority == "high"
        assert len(results[0].resources) == 2

    @pytest.mark.asyncio
    async def test_respects_count_parameter(self):
        provider = _make_provider_mock(json.dumps(SAMPLE_ITEMS))
        profile = _make_profile()
        results = await generate_recommendations(profile, provider, count=1)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_calls_provider_chat(self):
        provider = _make_provider_mock(json.dumps(SAMPLE_ITEMS[:1]))
        profile = _make_profile()
        await generate_recommendations(profile, provider, count=3)
        provider.chat.assert_awaited_once()
        args = provider.chat.call_args
        messages = args[0][0]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty_list(self):
        provider = _make_provider_mock("")
        profile = _make_profile()
        results = await generate_recommendations(profile, provider, count=5)
        assert results == []


# ===========================================================================
# 3. Recommendation model tests
# ===========================================================================


class TestRecommendationModel:
    def test_default_values(self):
        rec = Recommendation(topic="Test", reason="Because")
        assert rec.resources == []
        assert rec.expected_benefit == ""
        assert rec.priority == "medium"

    def test_model_dump(self):
        rec = Recommendation(
            topic="Docker Compose",
            reason="Container orchestration",
            resources=["docs.docker.com"],
            expected_benefit="Faster deployments",
            priority="high",
        )
        data = rec.model_dump(mode="json")
        assert data["topic"] == "Docker Compose"
        assert data["reason"] == "Container orchestration"
        assert data["resources"] == ["docs.docker.com"]
        assert data["expected_benefit"] == "Faster deployments"
        assert data["priority"] == "high"

    def test_model_dump_roundtrip(self):
        rec = Recommendation(
            topic="GraphQL",
            reason="API flexibility",
            resources=["spec", "tutorial"],
            expected_benefit="Better APIs",
            priority="low",
        )
        data = rec.model_dump(mode="json")
        rec2 = Recommendation(**data)
        assert rec == rec2
