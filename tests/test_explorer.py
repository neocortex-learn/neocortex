from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.explorer import (
    ArticleEntry,
    batch_scan_articles,
    extract_article_links,
)
from neocortex.models import DomainSkill, Language, Profile, Skills


SAMPLE_HTML = """<!DOCTYPE html>
<html>
<head><title>Test Blog</title></head>
<body>
<nav>
  <a href="/">Home</a>
  <a href="/about">About</a>
</nav>
<main>
  <article>
    <a href="/posts/async-python">Understanding Async Python</a>
    <p>A deep dive into asyncio.</p>
  </article>
  <article>
    <a href="/posts/react-hooks">React Hooks Explained</a>
  </article>
  <article>
    <a href="/posts/database-indexing">Database Indexing Strategies</a>
  </article>
  <a href="/posts/short">OK</a>
  <a href="/assets/style.css">Stylesheet</a>
  <a href="/images/logo.png">Logo</a>
  <a href="javascript:void(0)">Click</a>
  <a href="#section">Jump</a>
  <a href="https://external.com/other">External Link</a>
  <a href="/posts/async-python">Understanding Async Python</a>
</main>
</body>
</html>"""


def _mock_httpx_response(text: str, status_code: int = 200):
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


class TestExtractArticleLinks:
    @pytest.mark.asyncio
    async def test_extracts_article_links(self):
        resp = _mock_httpx_response(SAMPLE_HTML)

        with patch("neocortex.explorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            articles = await extract_article_links("https://example.com/blog")

        titles = [a.title for a in articles]
        assert "Understanding Async Python" in titles
        assert "React Hooks Explained" in titles
        assert "Database Indexing Strategies" in titles
        assert "About" not in titles  # 导航链接应被过滤

    @pytest.mark.asyncio
    async def test_filters_non_article_links(self):
        resp = _mock_httpx_response(SAMPLE_HTML)

        with patch("neocortex.explorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            articles = await extract_article_links("https://example.com/blog")

        urls = [a.url for a in articles]
        assert not any(u.endswith(".css") for u in urls)
        assert not any(u.endswith(".png") for u in urls)
        assert not any("javascript:" in u for u in urls)
        assert not any("external.com" in u for u in urls)

    @pytest.mark.asyncio
    async def test_deduplicates_links(self):
        resp = _mock_httpx_response(SAMPLE_HTML)

        with patch("neocortex.explorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            articles = await extract_article_links("https://example.com/blog")

        async_urls = [a.url for a in articles if "async-python" in a.url]
        assert len(async_urls) == 1

    @pytest.mark.asyncio
    async def test_filters_short_titles(self):
        resp = _mock_httpx_response(SAMPLE_HTML)

        with patch("neocortex.explorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            articles = await extract_article_links("https://example.com/blog")

        titles = [a.title for a in articles]
        assert "OK" not in titles

    @pytest.mark.asyncio
    async def test_empty_page(self):
        resp = _mock_httpx_response("<html><body>No links here</body></html>")

        with patch("neocortex.explorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            articles = await extract_article_links("https://example.com/empty")

        assert articles == []

    @pytest.mark.asyncio
    async def test_http_error_propagates(self):
        resp = _mock_httpx_response("", status_code=404)

        with patch("neocortex.explorer.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(Exception):
                await extract_article_links("https://example.com/404")


class TestBatchScanArticles:
    @pytest.mark.asyncio
    async def test_normal_ranking(self):
        articles = [
            ArticleEntry(title="Understanding Async Python", url="https://example.com/async"),
            ArticleEntry(title="CSS Grid Tips", url="https://example.com/css"),
            ArticleEntry(title="Database Indexing", url="https://example.com/db"),
        ]
        profile = Profile(skills=Skills(
            domains={"backend": DomainSkill(gaps=["async_programming", "database_optimization"])},
        ))

        llm_response = json.dumps({
            "author_overview": "Backend-focused blog",
            "articles": [
                {"index": 0, "priority": "P0", "reason": "Fills async gap"},
                {"index": 1, "priority": "P2", "reason": "Not backend related"},
                {"index": 2, "priority": "P0", "reason": "Fills DB gap"},
            ],
        })

        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=llm_response)

        overview, results = await batch_scan_articles(articles, profile, provider, Language.EN)

        assert overview == "Backend-focused blog"
        assert len(results) == 3
        assert results[0]["priority"] == "P0"
        assert results[-1]["priority"] == "P2"
        p0_titles = [r["title"] for r in results if r["priority"] == "P0"]
        assert "Understanding Async Python" in p0_titles
        assert "Database Indexing" in p0_titles

    @pytest.mark.asyncio
    async def test_llm_failure_degrades_gracefully(self):
        articles = [
            ArticleEntry(title="Article A", url="https://example.com/a"),
            ArticleEntry(title="Article B", url="https://example.com/b"),
        ]
        profile = Profile()

        provider = AsyncMock()
        provider.chat = AsyncMock(side_effect=Exception("LLM error"))

        overview, results = await batch_scan_articles(articles, profile, provider, Language.EN)

        assert overview == ""
        assert len(results) == 2
        assert all(r["priority"] == "P1" for r in results)

    @pytest.mark.asyncio
    async def test_empty_articles(self):
        provider = AsyncMock()
        overview, results = await batch_scan_articles([], Profile(), provider, Language.EN)
        assert overview == ""
        assert results == []

    @pytest.mark.asyncio
    async def test_invalid_json_degrades(self):
        articles = [
            ArticleEntry(title="Article A", url="https://example.com/a"),
        ]
        profile = Profile()

        provider = AsyncMock()
        provider.chat = AsyncMock(return_value="not valid json at all")

        overview, results = await batch_scan_articles(articles, profile, provider, Language.EN)

        assert len(results) == 1
        assert results[0]["priority"] == "P1"

    @pytest.mark.asyncio
    async def test_partial_llm_response(self):
        articles = [
            ArticleEntry(title="Article A", url="https://example.com/a"),
            ArticleEntry(title="Article B", url="https://example.com/b"),
            ArticleEntry(title="Article C", url="https://example.com/c"),
        ]
        profile = Profile()

        llm_response = json.dumps({
            "author_overview": "Tech blog",
            "articles": [
                {"index": 0, "priority": "P0", "reason": "Great"},
            ],
        })

        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=llm_response)

        overview, results = await batch_scan_articles(articles, profile, provider, Language.EN)

        assert len(results) == 3
        priorities = {r["title"]: r["priority"] for r in results}
        assert priorities["Article A"] == "P0"
        assert priorities["Article B"] == "P1"
        assert priorities["Article C"] == "P1"

    @pytest.mark.asyncio
    async def test_invalid_priority_normalized(self):
        articles = [
            ArticleEntry(title="Article A", url="https://example.com/a"),
        ]
        profile = Profile()

        llm_response = json.dumps({
            "author_overview": "",
            "articles": [
                {"index": 0, "priority": "HIGH", "reason": "Important"},
            ],
        })

        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=llm_response)

        _, results = await batch_scan_articles(articles, profile, provider, Language.EN)

        assert results[0]["priority"] == "P1"
