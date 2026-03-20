"""Tests for the interactive Q&A module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from neocortex.asker import ChatSession, ask_question
from neocortex.models import Language, LanguageSkill, Persona, Profile, SkillLevel, Skills


@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    provider.chat.return_value = "这是一个个性化的回答。"
    provider.max_context_tokens = MagicMock(return_value=128_000)
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


class TestChatSession:
    @pytest.mark.asyncio
    async def test_chat_session_maintains_history(self, mock_provider, sample_profile):
        mock_provider.chat.side_effect = ["回答一", "回答二", "回答三"]
        session = ChatSession(sample_profile, mock_provider, Language.ZH)

        r1 = await session.send("问题一")
        assert r1 == "回答一"

        r2 = await session.send("问题二")
        assert r2 == "回答二"

        r3 = await session.send("问题三")
        assert r3 == "回答三"

        history = session.history
        assert history[0]["role"] == "system"
        assert history[1] == {"role": "user", "content": "问题一"}
        assert history[2] == {"role": "assistant", "content": "回答一"}
        assert history[3] == {"role": "user", "content": "问题二"}
        assert history[4] == {"role": "assistant", "content": "回答二"}
        assert history[5] == {"role": "user", "content": "问题三"}
        assert history[6] == {"role": "assistant", "content": "回答三"}
        assert len(history) == 7

        assert mock_provider.chat.call_count == 3

    @pytest.mark.asyncio
    async def test_chat_session_system_prompt(self, mock_provider, sample_profile):
        session = ChatSession(sample_profile, mock_provider, Language.EN)

        await session.send("hi")
        messages = mock_provider.chat.call_args[0][0]
        system = messages[0]["content"]
        assert "Python" in system
        assert "expert" in system
        assert "English" in system

    @pytest.mark.asyncio
    async def test_chat_session_history_property_returns_copy(self, mock_provider, sample_profile):
        session = ChatSession(sample_profile, mock_provider, Language.EN)

        await session.send("hello")

        h1 = session.history
        h2 = session.history
        assert h1 == h2
        assert h1 is not h2

    @pytest.mark.asyncio
    async def test_chat_session_trims_history_when_exceeding_budget(self, mock_provider, sample_profile):
        mock_provider.max_context_tokens = MagicMock(return_value=100)

        long_text = "x" * 500
        mock_provider.chat.side_effect = [long_text, long_text, "short"]

        session = ChatSession(sample_profile, mock_provider, Language.EN)

        await session.send("first")
        await session.send("second")
        await session.send("third")

        history = session.history
        assert history[0]["role"] == "system"
        roles = [m["role"] for m in history[1:]]
        assert "user" in roles

    @pytest.mark.asyncio
    async def test_chat_session_always_keeps_system_prompt(self, mock_provider, sample_profile):
        mock_provider.max_context_tokens = MagicMock(return_value=50)

        long_text = "y" * 300
        mock_provider.chat.side_effect = [long_text, long_text, "ok"]

        session = ChatSession(sample_profile, mock_provider, Language.ZH)

        await session.send("a" * 200)
        await session.send("b" * 200)
        await session.send("c")

        history = session.history
        assert history[0]["role"] == "system"
        assert "Python" in history[0]["content"]
