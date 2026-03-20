"""Tests for the interactive Q&A module."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from neocortex.asker import ask_question
from neocortex.models import Language, Profile, Persona, Skills, LanguageSkill, SkillLevel


@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    provider.chat.return_value = "这是一个个性化的回答。"
    return provider


@pytest.fixture
def sample_profile():
    return Profile(
        skills=Skills(
            languages={"Python": LanguageSkill(level=SkillLevel.EXPERT, lines=50000)},
        ),
        persona=Persona(language=Language.ZH),
    )


class TestAskQuestion:
    @pytest.mark.asyncio
    async def test_returns_llm_response(self, mock_provider, sample_profile):
        result = await ask_question("什么是乐观锁？", sample_profile, mock_provider, Language.ZH)
        assert result == "这是一个个性化的回答。"

    @pytest.mark.asyncio
    async def test_calls_provider_with_messages(self, mock_provider, sample_profile):
        await ask_question("test question", sample_profile, mock_provider, Language.EN)
        mock_provider.chat.assert_called_once()
        args = mock_provider.chat.call_args
        messages = args[0][0]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "test question"

    @pytest.mark.asyncio
    async def test_system_prompt_contains_profile(self, mock_provider, sample_profile):
        await ask_question("q", sample_profile, mock_provider, Language.EN)
        messages = mock_provider.chat.call_args[0][0]
        system = messages[0]["content"]
        assert "Python" in system
        assert "expert" in system

    @pytest.mark.asyncio
    async def test_chinese_language_instruction(self, mock_provider, sample_profile):
        await ask_question("q", sample_profile, mock_provider, Language.ZH)
        system = mock_provider.chat.call_args[0][0][0]["content"]
        assert "中文" in system

    @pytest.mark.asyncio
    async def test_english_language_instruction(self, mock_provider, sample_profile):
        await ask_question("q", sample_profile, mock_provider, Language.EN)
        system = mock_provider.chat.call_args[0][0][0]["content"]
        assert "English" in system
