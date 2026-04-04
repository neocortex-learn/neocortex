from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.config import load_clips, save_clip, _parse_clip_file
from neocortex.models import Clip, DomainSkill, Language, Profile, Skills


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)


class TestClipModel:
    def test_defaults(self):
        c = Clip(id="abc12345", source="manual", content="hello")
        assert c.clip_type == "thought"
        assert c.status == "inbox"
        assert c.auto_tags == []
        assert c.related_concepts == []
        assert c.summary == ""
        assert c.relevance == ""
        assert c.priority == ""
        assert c.topic == ""
        assert c.processed_at is None
        assert c.promoted_to is None
        assert c.next_surface == ""
        assert c.surface_count == 0

    def test_full_fields(self):
        c = Clip(
            id="x1",
            source="https://example.com",
            content="some text",
            title="Example",
            clip_type="bookmark",
            auto_tags=["python", "async"],
            related_concepts=["concurrency"],
            status="reference",
            summary="About async",
            relevance="Relevant to your gaps",
            priority="P1",
            topic="backend",
            created_at="2026-04-03",
            processed_at="2026-04-03",
            promoted_to="notes/async.md",
            next_surface="2026-04-06",
            surface_count=2,
        )
        assert c.clip_type == "bookmark"
        assert c.priority == "P1"
        assert c.surface_count == 2


class TestFetchClipContent:
    @pytest.mark.asyncio
    async def test_plain_text(self):
        from neocortex.clipper import fetch_clip_content

        result = await fetch_clip_content("just a random thought")
        assert result["clip_type"] == "thought"
        assert result["source"] == "manual"
        assert result["content"] == "just a random thought"

    @pytest.mark.asyncio
    async def test_url_detection(self):
        from neocortex.clipper import fetch_clip_content

        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Test Page</title></head><body><p>Hello world</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await fetch_clip_content("https://example.com/article")
            assert result["clip_type"] == "bookmark"
            assert result["source"] == "https://example.com/article"

    @pytest.mark.asyncio
    async def test_tweet_url(self):
        from neocortex.clipper import fetch_clip_content

        mock_response = MagicMock()
        mock_response.text = "<html><head><title>Tweet</title></head><body><p>Tweet content</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await fetch_clip_content("https://x.com/user/status/12345")
            assert result["clip_type"] == "tweet"

    @pytest.mark.asyncio
    async def test_url_fetch_failure(self):
        import httpx
        from neocortex.clipper import fetch_clip_content

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.HTTPError("fail"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await fetch_clip_content("https://broken.example.com")
            assert result["clip_type"] == "bookmark"
            assert result["source"] == "https://broken.example.com"


class TestProcessClip:
    @pytest.mark.asyncio
    async def test_normal_return(self):
        from neocortex.clipper import process_clip

        profile = Profile(skills=Skills(
            domains={"backend": DomainSkill(gaps=["caching"])},
        ))
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=json.dumps({
            "summary": "About caching patterns",
            "relevance": "Directly addresses your caching gap",
            "related_concepts": ["redis"],
            "auto_tags": ["caching", "performance", "backend"],
            "topic": "backend",
        }))

        result = await process_clip(
            "Redis caching strategies for high traffic",
            "Redis Caching",
            profile,
            provider,
            Language.EN,
        )
        assert result["summary"] == "About caching patterns"
        assert result["topic"] == "backend"
        assert len(result["auto_tags"]) == 3

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self):
        from neocortex.clipper import process_clip

        profile = Profile(skills=Skills(
            domains={"backend": DomainSkill(gaps=["caching"])},
        ))
        provider = AsyncMock()
        provider.chat = AsyncMock(side_effect=Exception("LLM down"))

        result = await process_clip(
            "Redis caching strategies for high traffic backend systems",
            "Redis Caching",
            profile,
            provider,
            Language.EN,
        )
        assert result["topic"] == "backend"
        assert isinstance(result["auto_tags"], list)
        assert result["summary"] == ""


class TestSaveClip:
    def test_file_generation(self, tmp_path):
        c = Clip(
            id="abc12345",
            source="https://example.com",
            content="Test content here",
            title="Test Article",
            clip_type="bookmark",
            auto_tags=["python", "testing"],
            related_concepts=["pytest"],
            status="inbox",
            summary="A test",
            relevance="Good for testing skills",
            topic="backend",
            created_at="2026-04-03",
            next_surface="2026-04-06",
        )
        path = save_clip(tmp_path, c)
        assert path.exists()
        assert path.suffix == ".md"
        assert "2026-04-03" in path.name

        text = path.read_text(encoding="utf-8")
        assert "---" in text
        assert "id: abc12345" in text
        assert "clip_type: bookmark" in text
        assert "Test content here" in text
        assert '"python"' in text
        assert '"pytest"' in text

    def test_creates_clips_dir(self, tmp_path):
        c = Clip(id="x1", source="manual", content="hi", created_at="2026-01-01")
        clips_dir = tmp_path / "clips"
        assert not clips_dir.exists()
        save_clip(tmp_path, c)
        assert clips_dir.exists()


class TestLoadClips:
    def test_multiple_files(self, tmp_path):
        for i in range(3):
            c = Clip(
                id=f"id{i}",
                source="manual",
                content=f"Content {i}",
                title=f"Title {i}",
                created_at="2026-04-03",
            )
            save_clip(tmp_path, c)

        loaded = load_clips(tmp_path)
        assert len(loaded) == 3
        ids = {c.id for c in loaded}
        assert ids == {"id0", "id1", "id2"}

    def test_empty_dir(self, tmp_path):
        loaded = load_clips(tmp_path)
        assert loaded == []

    def test_no_clips_dir(self, tmp_path):
        loaded = load_clips(tmp_path)
        assert loaded == []

    def test_invalid_file_skipped(self, tmp_path):
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()
        (clips_dir / "bad.md").write_text("no frontmatter here", encoding="utf-8")
        c = Clip(id="good1", source="manual", content="Good", created_at="2026-04-03")
        save_clip(tmp_path, c)

        loaded = load_clips(tmp_path)
        assert len(loaded) == 1
        assert loaded[0].id == "good1"


class TestParseClipFile:
    def test_roundtrip(self, tmp_path):
        c = Clip(
            id="rt1",
            source="https://example.com",
            content="Roundtrip test",
            title="Roundtrip",
            clip_type="bookmark",
            auto_tags=["a", "b"],
            related_concepts=["concept_x"],
            summary="A summary",
            relevance="Relevant",
            topic="backend",
            created_at="2026-04-03",
            next_surface="2026-04-06",
            surface_count=3,
        )
        path = save_clip(tmp_path, c)
        parsed = _parse_clip_file(path)
        assert parsed is not None
        assert parsed.id == "rt1"
        assert parsed.source == "https://example.com"
        assert parsed.clip_type == "bookmark"
        assert parsed.auto_tags == ["a", "b"]
        assert parsed.related_concepts == ["concept_x"]
        assert parsed.summary == "A summary"
        assert parsed.topic == "backend"
        assert parsed.surface_count == 3

    def test_missing_id_returns_none(self, tmp_path):
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()
        f = clips_dir / "bad.md"
        f.write_text("---\nsource: manual\n---\nno id", encoding="utf-8")
        assert _parse_clip_file(f) is None


class TestClipCommand:
    def test_no_crash_text_input(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner
        from neocortex.cli import app

        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)

        runner = CliRunner()
        result = runner.invoke(app, ["clip", "just a thought about python"])
        assert result.exit_code == 0

    def test_no_crash_empty(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner
        from neocortex.cli import app

        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)

        runner = CliRunner()
        result = runner.invoke(app, ["clip"])
        assert result.exit_code == 0
