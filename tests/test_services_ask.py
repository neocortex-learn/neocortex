"""Tests for services.ask — warnings channel for non-fatal insight-eval failures."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.models import (
    AppConfig,
    Language,
    OutputSettings,
    Profile,
    ProviderType,
    Skills,
)


def _make_cfg() -> AppConfig:
    return AppConfig(
        provider=ProviderType.CLAUDE,
        api_key="test-key",
        output_settings=OutputSettings(),
    )


def _make_profile() -> Profile:
    return Profile(skills=Skills(domains={}))


@pytest.mark.asyncio
async def test_ask_success_has_no_warnings(tmp_path):
    from neocortex.services.ask import ask_question

    with (
        patch("neocortex.llm.create_provider", return_value=MagicMock()),
        patch("neocortex.asker.ask_question", new=AsyncMock(return_value="answer")),
        patch("neocortex.asker.evaluate_insight_value", new=AsyncMock(return_value=False)),
        patch("neocortex.config.append_log"),
    ):
        result = await ask_question(
            "q?", notes_dir=tmp_path, cfg=_make_cfg(),
            profile=_make_profile(), lang=Language.ZH,
        )

    assert not result.aborted
    assert result.warnings == []
    assert result.saved_as_insight is None


@pytest.mark.asyncio
async def test_ask_eval_failure_surfaces_warning(tmp_path):
    """评估调用炸掉时：回答保留、不存洞察，但 warnings 里能看到失败原因。"""
    from neocortex.services.ask import ask_question

    with (
        patch("neocortex.llm.create_provider", return_value=MagicMock()),
        patch("neocortex.asker.ask_question", new=AsyncMock(return_value="answer")),
        patch(
            "neocortex.asker.evaluate_insight_value",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        patch("neocortex.config.append_log"),
    ):
        result = await ask_question(
            "q?", notes_dir=tmp_path, cfg=_make_cfg(),
            profile=_make_profile(), lang=Language.ZH,
        )

    assert not result.aborted
    assert result.answer == "answer"
    assert result.saved_as_insight is None
    assert len(result.warnings) == 1
    assert "boom" in result.warnings[0]


@pytest.mark.asyncio
async def test_ask_save_failure_surfaces_warning(tmp_path):
    """评估通过但 save_insight 写盘失败：同样进 warnings 而不是静默。"""
    from neocortex.services.ask import ask_question

    with (
        patch("neocortex.llm.create_provider", return_value=MagicMock()),
        patch("neocortex.asker.ask_question", new=AsyncMock(return_value="answer")),
        patch("neocortex.asker.evaluate_insight_value", new=AsyncMock(return_value=True)),
        patch("neocortex.asker.save_insight", side_effect=OSError("disk full")),
        patch("neocortex.config.append_log"),
    ):
        result = await ask_question(
            "q?", notes_dir=tmp_path, cfg=_make_cfg(),
            profile=_make_profile(), lang=Language.ZH,
        )

    assert not result.aborted
    assert result.saved_as_insight is None
    assert len(result.warnings) == 1
    assert "disk full" in result.warnings[0]
