from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.config import (
    load_feed_history,
    load_feeds,
    save_feed_history,
    save_feeds,
)
from neocortex.feeder import FeedItem, _collect_gaps, _keyword_fallback, fetch_feeds, filter_by_gaps
from neocortex.models import DomainSkill, IntegrationSkill, Language, Profile, Skills


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Blog</title>
    <link>https://example.com</link>
    <item>
      <title>Understanding Async Python</title>
      <link>https://example.com/async-python</link>
      <guid>https://example.com/async-python</guid>
      <pubDate>Mon, 01 Apr 2026 00:00:00 GMT</pubDate>
      <description>A deep dive into asyncio and Python concurrency.</description>
    </item>
    <item>
      <title>React Server Components Explained</title>
      <link>https://example.com/react-rsc</link>
      <guid>https://example.com/react-rsc</guid>
      <pubDate>Sun, 31 Mar 2026 00:00:00 GMT</pubDate>
      <description>How React Server Components work under the hood.</description>
    </item>
    <item>
      <title>Database Indexing Strategies</title>
      <link>https://example.com/db-indexing</link>
      <guid>https://example.com/db-indexing</guid>
      <pubDate>Sat, 30 Mar 2026 00:00:00 GMT</pubDate>
      <description>Optimize your queries with proper indexing.</description>
    </item>
  </channel>
</rss>"""


class TestFeedConfig:
    def test_save_and_load_feeds(self):
        feeds = [
            {"url": "https://example.com/feed.xml", "name": "Example"},
            {"url": "https://blog.com/rss", "name": "Blog"},
        ]
        save_feeds(feeds)
        loaded = load_feeds()
        assert len(loaded) == 2
        assert loaded[0]["url"] == "https://example.com/feed.xml"
        assert loaded[1]["name"] == "Blog"

    def test_load_feeds_empty(self):
        feeds = load_feeds()
        assert feeds == []

    def test_load_feeds_invalid_json(self, tmp_path):
        (tmp_path / "feeds.json").write_text("not json", encoding="utf-8")
        feeds = load_feeds()
        assert feeds == []

    def test_load_feeds_filters_invalid_entries(self):
        save_feeds([
            {"url": "https://valid.com/feed"},
            {"name": "no url"},
            "string_entry",
        ])
        loaded = load_feeds()
        assert len(loaded) == 1
        assert loaded[0]["url"] == "https://valid.com/feed"

    def test_save_and_load_feed_history(self):
        history = {
            "https://example.com/feed.xml": "id-123",
            "https://blog.com/rss": "id-456",
        }
        save_feed_history(history)
        loaded = load_feed_history()
        assert loaded == history

    def test_load_feed_history_empty(self):
        history = load_feed_history()
        assert history == {}

    def test_feed_history_dedup(self):
        history = {"https://example.com/feed.xml": "old-id"}
        save_feed_history(history)
        loaded = load_feed_history()
        assert loaded["https://example.com/feed.xml"] == "old-id"

        history["https://example.com/feed.xml"] = "new-id"
        save_feed_history(history)
        loaded = load_feed_history()
        assert loaded["https://example.com/feed.xml"] == "new-id"

    def test_add_and_remove_feed(self):
        feeds = [{"url": "https://a.com/rss", "name": "A"}]
        save_feeds(feeds)

        loaded = load_feeds()
        loaded.append({"url": "https://b.com/rss", "name": "B"})
        save_feeds(loaded)

        loaded = load_feeds()
        assert len(loaded) == 2

        filtered = [f for f in loaded if f["url"] != "https://a.com/rss"]
        save_feeds(filtered)

        loaded = load_feeds()
        assert len(loaded) == 1
        assert loaded[0]["url"] == "https://b.com/rss"


class TestFetchFeeds:
    @pytest.mark.asyncio
    async def test_fetch_feeds_returns_items(self):
        mock_response = MagicMock()
        mock_response.text = SAMPLE_RSS
        mock_response.raise_for_status = MagicMock()

        with patch("neocortex.feeder.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            feeds = [{"url": "https://example.com/feed.xml", "name": "Test"}]
            items, history = await fetch_feeds(feeds, {})

            assert len(items) == 3
            assert items[0].title == "Understanding Async Python"
            assert items[0].url == "https://example.com/async-python"
            assert items[0].feed_name == "Test"
            assert "https://example.com/feed.xml" in history

    @pytest.mark.asyncio
    async def test_fetch_feeds_skips_seen(self):
        mock_response = MagicMock()
        mock_response.text = SAMPLE_RSS
        mock_response.raise_for_status = MagicMock()

        with patch("neocortex.feeder.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            history = {"https://example.com/feed.xml": "https://example.com/react-rsc"}
            feeds = [{"url": "https://example.com/feed.xml", "name": "Test"}]
            items, _ = await fetch_feeds(feeds, history)

            assert len(items) == 1
            assert items[0].title == "Understanding Async Python"

    @pytest.mark.asyncio
    async def test_fetch_feeds_empty_list(self):
        items, history = await fetch_feeds([], {})
        assert items == []
        assert history == {}

    @pytest.mark.asyncio
    async def test_fetch_feeds_handles_error(self):
        with patch("neocortex.feeder.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("network error"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            feeds = [{"url": "https://broken.com/feed.xml", "name": "Broken"}]
            items, history = await fetch_feeds(feeds, {})

            assert items == []


class TestKeywordFallback:
    def test_matches_gap_words_in_title(self):
        items = [
            FeedItem(title="Understanding Async Python", url="u1", feed_name="F", published="", summary=""),
            FeedItem(title="CSS Grid Layout Tips", url="u2", feed_name="F", published="", summary=""),
            FeedItem(title="Database Indexing", url="u3", feed_name="F", published="", summary=""),
        ]
        gaps = ["async_programming", "database_optimization"]
        result = _keyword_fallback(items, gaps, 10)

        titles = [r.title for r in result]
        assert "Understanding Async Python" in titles
        assert "Database Indexing" in titles

    def test_empty_items(self):
        result = _keyword_fallback([], ["some_gap"], 10)
        assert result == []

    def test_no_matching_gaps(self):
        items = [
            FeedItem(title="Cooking Recipes", url="u1", feed_name="F", published="", summary=""),
        ]
        result = _keyword_fallback(items, ["async_programming"], 10)
        assert result == []

    def test_respects_max_results(self):
        items = [
            FeedItem(title=f"Python tip {i}", url=f"u{i}", feed_name="F", published="", summary="")
            for i in range(20)
        ]
        result = _keyword_fallback(items, ["python"], 3)
        assert len(result) == 3


class TestFilterByGaps:
    @pytest.mark.asyncio
    async def test_no_gaps_returns_truncated(self):
        items = [
            FeedItem(title=f"Article {i}", url=f"u{i}", feed_name="F", published="", summary="")
            for i in range(15)
        ]
        profile = Profile()
        result = await filter_by_gaps(items, profile, None, Language.EN, max_results=5)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_empty_items(self):
        profile = Profile(skills=Skills(
            domains={"backend": DomainSkill(gaps=["caching"])},
        ))
        result = await filter_by_gaps([], profile, None, Language.EN)
        assert result == []

    @pytest.mark.asyncio
    async def test_keyword_fallback_used_without_provider(self):
        items = [
            FeedItem(title="Redis Caching Patterns", url="u1", feed_name="F", published="", summary=""),
            FeedItem(title="Cooking Tips", url="u2", feed_name="F", published="", summary=""),
        ]
        profile = Profile(skills=Skills(
            domains={"backend": DomainSkill(gaps=["caching", "redis"])},
        ))
        result = await filter_by_gaps(items, profile, None, Language.EN)
        assert len(result) >= 1
        assert result[0].title == "Redis Caching Patterns"


class TestCollectGaps:
    def test_collects_from_domains_and_integrations(self):
        profile = Profile(skills=Skills(
            domains={
                "backend": DomainSkill(gaps=["caching", "message_queue"]),
                "frontend": DomainSkill(gaps=["ssr"]),
            },
            integrations={
                "aws": IntegrationSkill(gaps=["lambda"]),
            },
        ))
        gaps = _collect_gaps(profile)
        assert set(gaps) == {"caching", "message_queue", "ssr", "lambda"}

    def test_deduplicates(self):
        profile = Profile(skills=Skills(
            domains={
                "a": DomainSkill(gaps=["caching"]),
                "b": DomainSkill(gaps=["caching"]),
            },
        ))
        gaps = _collect_gaps(profile)
        assert gaps.count("caching") == 1

    def test_empty_profile(self):
        profile = Profile()
        gaps = _collect_gaps(profile)
        assert gaps == []
