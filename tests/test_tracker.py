"""Tests for recommendation tracking — matching, URL normalization, expiration."""

from __future__ import annotations

from neocortex.models import RecommendationRecord, Resource
from neocortex.tracker import (
    _extract_keywords,
    _normalize_url,
    expire_stale_recommendations,
    match_recommendation,
)


# ── Helpers ──


def _rec(
    topic: str = "pytest testing",
    url: str = "https://docs.pytest.org/en/latest/",
    created_at: str = "2026-03-21",
    **kwargs,
) -> RecommendationRecord:
    resources = [Resource(title=topic, url=url)] if url else []
    return RecommendationRecord(
        id="test-1",
        topic=topic,
        resources=resources,
        created_at=created_at,
        **kwargs,
    )


# ── URL normalization ──


class TestNormalizeUrl:
    def test_strips_scheme(self):
        assert _normalize_url("https://example.com/path") == "example.com/path"

    def test_strips_http(self):
        assert _normalize_url("http://example.com") == "example.com"

    def test_strips_query_params(self):
        assert _normalize_url("https://example.com/p?a=1&b=2") == "example.com/p"

    def test_strips_fragment(self):
        assert _normalize_url("https://example.com/p#section") == "example.com/p"

    def test_strips_trailing_slash(self):
        assert _normalize_url("https://example.com/path/") == "example.com/path"

    def test_lowercases(self):
        assert _normalize_url("https://Example.COM/Path") == "example.com/path"

    def test_already_normalized(self):
        assert _normalize_url("example.com/path") == "example.com/path"


# ── Keyword extraction ──


class TestExtractKeywords:
    def test_splits_spaces(self):
        assert _extract_keywords("pytest testing") == ["pytest", "testing"]

    def test_filters_short_tokens(self):
        assert _extract_keywords("a to pytest") == ["pytest"]

    def test_lowercases(self):
        assert _extract_keywords("Pytest Testing") == ["pytest", "testing"]

    def test_splits_hyphens_underscores(self):
        assert _extract_keywords("unit-testing_basics") == ["unit", "testing", "basics"]


# ── Level 1: Exact URL match ──


class TestMatchLevel1:
    def test_exact_match(self):
        rec = _rec()
        result = match_recommendation("https://docs.pytest.org/en/latest/", "title", [rec])
        assert result is rec

    def test_match_ignores_query_params(self):
        rec = _rec()
        result = match_recommendation("https://docs.pytest.org/en/latest/?ref=search", "title", [rec])
        assert result is rec

    def test_match_ignores_trailing_slash(self):
        rec = _rec(url="https://docs.pytest.org/en/latest")
        result = match_recommendation("https://docs.pytest.org/en/latest/", "title", [rec])
        assert result is rec

    def test_match_ignores_scheme(self):
        rec = _rec(url="http://docs.pytest.org/en/latest/")
        result = match_recommendation("https://docs.pytest.org/en/latest/", "title", [rec])
        assert result is rec

    def test_different_path_falls_to_level2(self):
        rec = _rec()
        result = match_recommendation("https://docs.pytest.org/en/7.0/fixtures.html", "Pytest Fixtures", [rec])
        assert result is rec  # Level 2 catches it (same domain + keyword "pytest")

    def test_local_file_exact_path(self):
        rec = _rec(url="/tmp/pytest-guide.pdf")
        result = match_recommendation("/tmp/pytest-guide.pdf", "title", [rec])
        assert result is rec


# ── Level 2: Domain + keyword match ──


class TestMatchLevel2:
    def test_same_domain_keyword_in_title(self):
        rec = _rec(topic="pytest fixtures", url="https://docs.pytest.org/main/")
        result = match_recommendation(
            "https://docs.pytest.org/en/latest/fixtures.html",
            "Pytest Fixtures Guide",
            [rec],
        )
        assert result is rec

    def test_same_domain_keyword_in_path(self):
        rec = _rec(topic="redis cluster", url="https://redis.io/docs/")
        result = match_recommendation(
            "https://redis.io/docs/manual/cluster-tutorial",
            "Redis Docs",
            [rec],
        )
        assert result is rec

    def test_different_domain_no_match(self):
        rec = _rec(topic="pytest fixtures", url="https://docs.pytest.org/main/")
        result = match_recommendation(
            "https://realpython.com/pytest-fixtures/",
            "Pytest Fixtures Guide",
            [rec],
        )
        assert result is None  # Different domain

    def test_skipped_for_local_files(self):
        rec = _rec(topic="pytest testing")
        result = match_recommendation("/tmp/pytest.pdf", "Pytest Guide", [rec])
        assert result is None  # Local files skip level 2


# ── Level 3: No match (caller handles confirmation) ──


class TestMatchLevel3:
    def test_returns_none_when_no_match(self):
        rec = _rec(topic="docker compose")
        result = match_recommendation(
            "https://completely-different.com/article",
            "Unrelated Article",
            [rec],
        )
        assert result is None

    def test_empty_pending_list(self):
        result = match_recommendation("https://example.com", "title", [])
        assert result is None

    def test_no_pending_returns_none(self):
        result = match_recommendation("https://example.com", "title", [])
        assert result is None


# ── Expiration ──


class TestExpireStale:
    def test_expires_old_pending(self):
        old = _rec(created_at="2025-01-01")
        result = expire_stale_recommendations([old])
        assert result[0].status == "skipped"

    def test_keeps_recent_pending(self):
        recent = _rec(created_at="2026-03-20")
        result = expire_stale_recommendations([recent])
        assert result[0].status == "pending"

    def test_skips_completed(self):
        completed = _rec(created_at="2025-01-01", status="completed")
        result = expire_stale_recommendations([completed])
        assert result[0].status == "completed"

    def test_custom_max_age(self):
        recent = _rec(created_at="2026-03-10")
        result = expire_stale_recommendations([recent], max_age_days=5)
        assert result[0].status == "skipped"
