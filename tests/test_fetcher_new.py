"""Tests for new fetcher features — Jina fallback, URL filter, image, EPUB."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.reader.fetcher import ContentFetcher, Document, Section


# ── URL safety filter ──


class TestIsPublicUrl:
    def test_public_url(self):
        assert ContentFetcher._is_public_url("https://docs.pytest.org/en/latest/") is True

    def test_localhost(self):
        assert ContentFetcher._is_public_url("http://localhost:3000/api") is False

    def test_127_0_0_1(self):
        assert ContentFetcher._is_public_url("http://127.0.0.1:8080/admin") is False

    def test_ipv6_loopback(self):
        assert ContentFetcher._is_public_url("http://[::1]:5000/") is False

    def test_dot_local(self):
        assert ContentFetcher._is_public_url("https://myapp.local/docs") is False

    def test_dot_internal(self):
        assert ContentFetcher._is_public_url("https://wiki.internal/page") is False

    def test_private_10_range(self):
        assert ContentFetcher._is_public_url("http://10.0.0.1/metrics") is False

    def test_private_172_range(self):
        assert ContentFetcher._is_public_url("http://172.16.0.1/api") is False

    def test_private_192_168(self):
        assert ContentFetcher._is_public_url("http://192.168.1.100/dashboard") is False

    def test_token_in_query(self):
        assert ContentFetcher._is_public_url("https://s3.aws.com/file?token=abc123") is False

    def test_key_in_query(self):
        assert ContentFetcher._is_public_url("https://api.example.com/data?api_key=secret") is False

    def test_signature_in_query(self):
        assert ContentFetcher._is_public_url("https://cdn.example.com/img?signature=abc") is False

    def test_safe_query_params(self):
        assert ContentFetcher._is_public_url("https://example.com/page?ref=google&lang=en") is True

    def test_no_host(self):
        assert ContentFetcher._is_public_url("") is True  # degenerate case, no host to block


# ── Jina fallback ──


class TestJinaFallback:
    def test_jina_parses_metadata_headers(self):
        fetcher = ContentFetcher()
        jina_response = (
            "Title: Test Article\n"
            "URL Source: https://example.com/article\n"
            "Markdown Content:\n"
            "\n"
            "# Test Article\n\n"
            "This is the article body with enough content to pass the 50-char threshold easily."
        )

        async def _run():
            with patch("httpx.AsyncClient") as MockClient:
                mock_resp = MagicMock()
                mock_resp.text = jina_response
                mock_resp.raise_for_status = MagicMock()
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client
                return await fetcher._fetch_url_jina("https://example.com/article")

        doc = asyncio.run(_run())
        assert doc is not None
        assert doc.title == "Test Article"
        assert "article body" in doc.content

    def test_jina_returns_none_on_short_response(self):
        fetcher = ContentFetcher()

        async def _run():
            with patch("httpx.AsyncClient") as MockClient:
                mock_resp = MagicMock()
                mock_resp.text = "short"
                mock_resp.raise_for_status = MagicMock()
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client
                return await fetcher._fetch_url_jina("https://example.com")

        doc = asyncio.run(_run())
        assert doc is None

    def test_jina_returns_none_on_http_error(self):
        fetcher = ContentFetcher()

        async def _run():
            import httpx
            with patch("httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client
                return await fetcher._fetch_url_jina("https://example.com")

        doc = asyncio.run(_run())
        assert doc is None

    def test_jina_extracts_title_from_heading_when_no_metadata(self):
        fetcher = ContentFetcher()

        async def _run():
            with patch("httpx.AsyncClient") as MockClient:
                mock_resp = MagicMock()
                mock_resp.text = "# My Article Title\n\nSome content that is long enough to pass the threshold check for minimum length."
                mock_resp.raise_for_status = MagicMock()
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client
                return await fetcher._fetch_url_jina("https://example.com/article")

        doc = asyncio.run(_run())
        assert doc is not None
        assert doc.title == "My Article Title"


# ── Image fetch ──


class TestImageFetch:
    def test_rejects_oversized_image(self, tmp_path: Path):
        img = tmp_path / "huge.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * (21 * 1024 * 1024))

        provider = AsyncMock()
        fetcher = ContentFetcher(provider=provider)

        with pytest.raises(ValueError, match="Image too large"):
            asyncio.run(fetcher._fetch_image(str(img)))

    def test_accepts_small_image(self, tmp_path: Path):
        img = tmp_path / "small.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 100)

        provider = AsyncMock()
        provider.describe_image = AsyncMock(return_value="A small image")
        fetcher = ContentFetcher(provider=provider)

        doc = asyncio.run(fetcher._fetch_image(str(img)))
        assert doc.title == "small"
        assert doc.content == "A small image"
        provider.describe_image.assert_called_once()

    def test_rejects_missing_file(self):
        provider = AsyncMock()
        fetcher = ContentFetcher(provider=provider)

        with pytest.raises(ValueError, match="File not found"):
            asyncio.run(fetcher._fetch_image("/nonexistent/image.png"))

    def test_rejects_without_provider(self, tmp_path: Path):
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG")
        fetcher = ContentFetcher()

        with pytest.raises(ValueError, match="LLM provider required"):
            asyncio.run(fetcher._fetch_image(str(img)))

    def test_correct_media_type(self, tmp_path: Path):
        for ext, expected_type in [(".jpg", "image/jpeg"), (".gif", "image/gif"), (".webp", "image/webp")]:
            img = tmp_path / f"test{ext}"
            img.write_bytes(b"\x00" * 10)
            provider = AsyncMock()
            provider.describe_image = AsyncMock(return_value="desc")
            fetcher = ContentFetcher(provider=provider)
            asyncio.run(fetcher._fetch_image(str(img)))
            call_args = provider.describe_image.call_args
            assert call_args[0][1] == expected_type


# ── EPUB reading ──


class TestEpubRead:
    def _make_epub(self, tmp_path: Path, title: str = "Test Book", chapters: list[tuple[str, str]] | None = None) -> Path:
        """Create a minimal EPUB file for testing."""
        from ebooklib import epub

        book = epub.EpubBook()
        book.set_identifier("test-id-123")
        book.set_title(title)
        book.set_language("en")

        if chapters is None:
            chapters = [
                ("Chapter 1", "<h1>Chapter 1</h1><p>First chapter content here.</p>"),
                ("Chapter 2", "<h1>Chapter 2</h1><p>Second chapter content here.</p>"),
            ]

        spine = ["nav"]
        for i, (ch_title, ch_content) in enumerate(chapters):
            ch = epub.EpubHtml(title=ch_title, file_name=f"ch{i}.xhtml")
            ch.set_content(ch_content.encode("utf-8"))
            book.add_item(ch)
            spine.append(ch)

        book.spine = spine
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        epub_path = tmp_path / "test.epub"
        epub.write_epub(str(epub_path), book)
        return epub_path

    def test_reads_epub_title(self, tmp_path: Path):
        epub_path = self._make_epub(tmp_path, title="My Test Book")
        fetcher = ContentFetcher()
        doc = fetcher._read_epub(str(epub_path))
        assert doc.title == "My Test Book"

    def test_extracts_chapters(self, tmp_path: Path):
        epub_path = self._make_epub(tmp_path)
        fetcher = ContentFetcher()
        doc = fetcher._read_epub(str(epub_path))
        assert len(doc.sections) >= 2
        assert "First chapter" in doc.content
        assert "Second chapter" in doc.content

    def test_extracts_chapter_titles(self, tmp_path: Path):
        epub_path = self._make_epub(tmp_path)
        fetcher = ContentFetcher()
        doc = fetcher._read_epub(str(epub_path))
        titles = [s.title for s in doc.sections if s.title]
        assert any("Chapter 1" in t for t in titles)

    def test_missing_epub_file(self):
        fetcher = ContentFetcher()
        with pytest.raises(ValueError, match="File not found"):
            fetcher._read_epub("/nonexistent/book.epub")

    def test_epub_with_no_title_metadata(self, tmp_path: Path):
        from ebooklib import epub

        book = epub.EpubBook()
        book.set_identifier("no-title")
        book.set_language("en")
        ch = epub.EpubHtml(title="Ch", file_name="ch.xhtml")
        ch.set_content(b"<p>Content</p>")
        book.add_item(ch)
        book.spine = ["nav", ch]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        epub_path = tmp_path / "notitle.epub"
        epub.write_epub(str(epub_path), book)

        fetcher = ContentFetcher()
        doc = fetcher._read_epub(str(epub_path))
        assert doc.title == "notitle"  # Falls back to stem


# ── Fetch dispatch ──


class TestFetchDispatch:
    def test_routes_epub(self, tmp_path: Path):
        fetcher = ContentFetcher()
        epub_path = tmp_path / "book.epub"
        with patch.object(fetcher, "_read_epub", return_value=Document(title="t", content="c", source="s")) as mock:
            asyncio.run(fetcher.fetch(str(epub_path)))
            mock.assert_called_once_with(str(epub_path))

    def test_routes_image(self, tmp_path: Path):
        fetcher = ContentFetcher(provider=AsyncMock())
        img_path = tmp_path / "photo.jpg"
        with patch.object(fetcher, "_fetch_image", new_callable=AsyncMock, return_value=Document(title="t", content="c", source="s")) as mock:
            asyncio.run(fetcher.fetch(str(img_path)))
            mock.assert_called_once_with(str(img_path))

    def test_routes_pdf(self):
        fetcher = ContentFetcher()
        with patch.object(fetcher, "_fetch_pdf", new_callable=AsyncMock, return_value=Document(title="t", content="c", source="s")) as mock:
            asyncio.run(fetcher.fetch("/tmp/doc.pdf"))
            mock.assert_called_once_with("/tmp/doc.pdf")

    def test_routes_url(self):
        fetcher = ContentFetcher()
        with patch.object(fetcher, "_fetch_url", new_callable=AsyncMock, return_value=Document(title="t", content="c", source="s")) as mock:
            asyncio.run(fetcher.fetch("https://example.com"))
            mock.assert_called_once_with("https://example.com")
