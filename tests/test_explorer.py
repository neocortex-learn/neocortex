from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.explorer import (
    ArticleEntry,
    batch_scan_articles,
    extract_article_links,
)
from neocortex.models import DomainSkill, Profile, Skills


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Test Blog</title>
  <link>https://example.com</link>
  <item>
    <title>Understanding Async Python</title>
    <link>https://example.com/posts/async-python</link>
    <description>A deep dive into asyncio and concurrency.</description>
  </item>
  <item>
    <title>React Hooks Explained</title>
    <link>https://example.com/posts/react-hooks</link>
    <description>Modern React patterns.</description>
  </item>
  <item>
    <title>Database Indexing Strategies</title>
    <link>https://example.com/posts/database-indexing</link>
    <description>How to make queries fast.</description>
  </item>
</channel>
</rss>"""

SAMPLE_HTML_WITH_FEED = """<!DOCTYPE html>
<html>
<head>
  <title>Test Blog</title>
  <link rel="alternate" type="application/rss+xml" href="/feeds/rss.xml">
</head>
<body><h1>Blog</h1></body>
</html>"""


def _mock_httpx_response(text: str, status_code: int = 200, content_type: str = "text/html"):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.headers = {"content-type": content_type}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


class TestExtractArticleLinks:
    @pytest.mark.asyncio
    async def test_parses_rss_feed(self):
        resp = _mock_httpx_response(SAMPLE_RSS, content_type="application/rss+xml")

        with patch("neocortex.explorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            articles = await extract_article_links("https://example.com/feeds/rss.xml")

        titles = [a.title for a in articles]
        assert len(articles) == 3
        assert "Understanding Async Python" in titles
        assert "React Hooks Explained" in titles
        assert articles[0].snippet  # should have snippet from description

    @pytest.mark.asyncio
    async def test_discovers_feed_from_html(self):
        html_resp = _mock_httpx_response(SAMPLE_HTML_WITH_FEED)
        rss_resp = _mock_httpx_response(SAMPLE_RSS, content_type="application/rss+xml")

        call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "rss.xml" in url:
                return rss_resp
            return html_resp

        with patch("neocortex.explorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            articles = await extract_article_links("https://example.com/blog")

        assert len(articles) == 3

    @pytest.mark.asyncio
    async def test_deduplicates(self):
        rss_with_dups = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Article A</title><link>https://example.com/a</link></item>
  <item><title>Article A</title><link>https://example.com/a</link></item>
  <item><title>Article B</title><link>https://example.com/b</link></item>
</channel></rss>"""
        resp = _mock_httpx_response(rss_with_dups, content_type="application/rss+xml")

        with patch("neocortex.explorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            articles = await extract_article_links("https://example.com/feed.xml")

        assert len(articles) == 2

    @pytest.mark.asyncio
    async def test_empty_page_no_feed(self):
        resp = _mock_httpx_response("<html><body>No feed here</body></html>")

        with patch("neocortex.explorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            articles = await extract_article_links("https://example.com/blog")

        assert articles == []

    @pytest.mark.asyncio
    async def test_http_error(self):
        resp = _mock_httpx_response("", status_code=404)

        with patch("neocortex.explorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(Exception):
                await extract_article_links("https://example.com/feed.xml")


# ── batch_scan_articles ──


@pytest.fixture
def sample_articles():
    return [
        ArticleEntry("Understanding Async Python", "https://example.com/async", "asyncio guide"),
        ArticleEntry("React Hooks Explained", "https://example.com/hooks", "React patterns"),
        ArticleEntry("Database Indexing", "https://example.com/db", "SQL optimization"),
    ]


@pytest.fixture
def profile():
    return Profile(
        skills=Skills(
            domains={
                "backend": DomainSkill(level="proficient", gaps=["async patterns", "database optimization"]),
            },
        ),
    )


class TestBatchScan:
    @pytest.mark.asyncio
    async def test_ranks_articles(self, sample_articles, profile):
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=json.dumps({
            "author_overview": "A tech blog about web development",
            "articles": [
                {"index": 0, "priority": "P0", "reason": "Directly addresses async patterns gap"},
                {"index": 1, "priority": "P2", "reason": "Frontend, not relevant"},
                {"index": 2, "priority": "P0", "reason": "Database optimization is an active gap"},
            ],
        }))

        overview, results = await batch_scan_articles(sample_articles, profile, provider)

        assert overview == "A tech blog about web development"
        assert results[0]["priority"] == "P0"
        assert results[-1]["priority"] == "P2"

    @pytest.mark.asyncio
    async def test_llm_failure_degrades_to_p1(self, sample_articles, profile):
        provider = AsyncMock()
        provider.chat = AsyncMock(side_effect=Exception("LLM error"))

        overview, results = await batch_scan_articles(sample_articles, profile, provider)

        assert overview == ""
        assert all(r["priority"] == "P1" for r in results)

    @pytest.mark.asyncio
    async def test_empty_articles(self, profile):
        provider = AsyncMock()
        overview, results = await batch_scan_articles([], profile, provider)
        assert overview == ""
        assert results == []

    @pytest.mark.asyncio
    async def test_invalid_json(self, sample_articles, profile):
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value="not json")

        overview, results = await batch_scan_articles(sample_articles, profile, provider)

        assert all(r["priority"] == "P1" for r in results)
