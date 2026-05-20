"""Tests for services.clip — console-free clip pipeline (Sprint 0 S0-1')."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.models import (
    AppConfig,
    DomainSkill,
    Language,
    OutputSettings,
    Profile,
    ProviderType,
    Skills,
)


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)


def _make_cfg(provider=None, api_key=None, default_process=True) -> AppConfig:
    return AppConfig(
        provider=provider,
        api_key=api_key,
        output_settings=OutputSettings(),
        clip_default_process=default_process,
    )


def _make_profile() -> Profile:
    return Profile(skills=Skills(domains={"backend": DomainSkill(gaps=["caching"])}))


class TestClipTextPlainText:
    """No URL, no LLM key configured → save with no process."""

    @pytest.mark.asyncio
    async def test_plain_text_no_llm(self, tmp_path):
        from neocortex.services.clip import clip_text

        result = await clip_text(
            "一段纯文字想法用来测 service 层",
            process=False,
            notes_dir=tmp_path,
            cfg=_make_cfg(),
            profile=_make_profile(),
            lang=Language.ZH,
        )

        assert result.aborted is False
        assert result.llm_status == "skipped_user_opt_out"
        assert result.saved_path != ""
        assert Path(result.saved_path).exists()
        assert result.clip.title != "", "title fallback (#4) 在 service 中也应生效"


class TestClipTextFetchFailure:
    """Hard fetch failure (404 / login wall) → aborted result, nothing saved."""

    @pytest.mark.asyncio
    async def test_aborted_on_404(self, tmp_path):
        import httpx
        from neocortex.services.clip import clip_text

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPError("404 Not Found")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await clip_text(
                "https://broken.example.com/",
                notes_dir=tmp_path,
                cfg=_make_cfg(),
                profile=_make_profile(),
                lang=Language.EN,
            )

        assert result.aborted is True
        assert "HTTP fetch failed" in (result.abort_reason or "")
        assert result.saved_path == ""
        # No file written
        clips_dir = tmp_path / "clips"
        assert not clips_dir.exists() or not list(clips_dir.glob("*.md"))

    @pytest.mark.asyncio
    async def test_image_path_aborted_until_service_supports_ocr(self, tmp_path):
        from neocortex.services.clip import clip_text

        image_path = tmp_path / "screenshot.png"
        image_path.write_bytes(b"not a real png, fetcher only checks path/ext")

        result = await clip_text(
            str(image_path),
            process=False,
            notes_dir=tmp_path,
            cfg=_make_cfg(),
            profile=_make_profile(),
            lang=Language.EN,
        )

        assert result.aborted is True
        assert "image OCR is not supported" in (result.abort_reason or "")
        assert result.saved_path == ""
        clips_dir = tmp_path / "clips"
        assert not clips_dir.exists() or not list(clips_dir.glob("*.md"))


class TestClipTextWeakFetch:
    """Short URL fetch → save bookmark + skip LLM (P2 fix carries to service)."""

    @pytest.mark.asyncio
    async def test_weak_fetch_skips_llm(self, tmp_path):
        from neocortex.services.clip import clip_text

        mock_resp = MagicMock()
        mock_resp.text = "<html><body>x</body></html>"
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await clip_text(
                "https://tiny.example.com/",
                process=True,  # 即便用户强制 --process 也应被 weak 拒绝
                notes_dir=tmp_path,
                cfg=_make_cfg(provider=ProviderType.CLAUDE, api_key="k"),
                profile=_make_profile(),
                lang=Language.EN,
            )

        assert result.aborted is False
        assert result.llm_status == "skipped_weak_fetch"
        assert result.saved_path != ""
        assert not result.clip.related_concepts, "weak fetch 不应产出 concept tags"


class TestClipTextLLMPath:
    """End-to-end with mocked LLM provider returning real concepts."""

    @pytest.mark.asyncio
    async def test_full_path_with_llm(self, tmp_path):
        from neocortex.services.clip import clip_text

        # Mock the provider chat to return structured concept JSON
        mock_provider = AsyncMock()
        mock_provider.chat = AsyncMock(return_value=json.dumps({
            "summary": "About async patterns",
            "relevance": "Useful for backend work",
            "related_concepts": ["asyncio", "concurrency"],
            "auto_tags": ["python", "async"],
            "topic": "backend",
        }))

        with patch("neocortex.llm.create_provider", return_value=mock_provider):
            result = await clip_text(
                "Python asyncio is great for IO-bound concurrent work",
                process=True,
                notes_dir=tmp_path,
                cfg=_make_cfg(provider=ProviderType.CLAUDE, api_key="k"),
                profile=_make_profile(),
                lang=Language.EN,
            )

        assert result.aborted is False
        assert result.llm_status == "ok"
        assert result.llm_error is None
        assert "asyncio" in result.clip.related_concepts
        assert result.clip.summary == "About async patterns"
        assert result.clip.topic == "backend"


class TestClipTextDefaultsFromConfig:
    """process=None → falls back to cfg.clip_default_process (Q11)."""

    @pytest.mark.asyncio
    async def test_default_off_skips_llm(self, tmp_path):
        from neocortex.services.clip import clip_text

        result = await clip_text(
            "一些纯文字",
            process=None,  # 用配置默认
            notes_dir=tmp_path,
            cfg=_make_cfg(default_process=False),  # 关掉默认
            profile=_make_profile(),
            lang=Language.ZH,
        )

        assert result.llm_status == "skipped_user_opt_out"

    @pytest.mark.asyncio
    async def test_default_on_no_key_skips(self, tmp_path):
        from neocortex.services.clip import clip_text

        result = await clip_text(
            "一些纯文字",
            process=None,
            notes_dir=tmp_path,
            cfg=_make_cfg(default_process=True),  # 默认开，但无 key
            profile=_make_profile(),
            lang=Language.ZH,
        )

        assert result.llm_status == "skipped_no_key"
