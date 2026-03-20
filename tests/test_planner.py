from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from neocortex.models import (
    Calibration,
    Language,
    LanguageSkill,
    DomainSkill,
    LearningGoal,
    Persona,
    Profile,
    SkillLevel,
    Skills,
)
from neocortex.planner import generate_plan, _clean_markdown


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_RECOMMENDATIONS = [
    {
        "topic": "WebSocket Reliability Design",
        "reason": "Your cutie-server project uses WebSocket but lacks reconnection logic",
        "resources": ["RFC 6455", "Socket.IO docs"],
        "expected_benefit": "WebSocket disconnect rate reduced by 80%",
        "priority": "high",
    },
    {
        "topic": "Distributed Observability",
        "reason": "Your projects lack structured logging and tracing",
        "resources": ["OpenTelemetry docs", "Grafana tutorials"],
        "expected_benefit": "Faster incident debugging across services",
        "priority": "medium",
    },
    {
        "topic": "Redis Cluster",
        "reason": "Your profile shows gaps in distributed caching",
        "resources": ["Redis docs", "https://redis.io/docs/management/scaling/"],
        "expected_benefit": "Better caching in your API project",
        "priority": "medium",
    },
]

SAMPLE_PLAN_EN = """# Personalized Learning Plan
> Generated: {date} | Based on your skill profile

## Goal
Improve system design and architecture skills, focusing on real-time communication reliability and distributed systems.

## Week 1: WebSocket Reliability Design
- [ ] Study RFC 6455 heartbeat mechanism
- [ ] Implement reconnection logic in cutie-server
- [ ] Write integration tests for disconnect scenarios
- Resource: Socket.IO official documentation
- Expected outcome: WebSocket disconnect rate reduced by 80%

## Week 2: Distributed Observability
- [ ] Set up OpenTelemetry in one microservice
- [ ] Add structured logging with correlation IDs
- [ ] Create a Grafana dashboard for key metrics
- Resource: OpenTelemetry docs, Grafana tutorials
- Expected outcome: Faster incident debugging across services

## Week 3: Redis Cluster
- [ ] Deploy a 3-node Redis Cluster locally
- [ ] Migrate cutie-server cache to Redis Cluster
- [ ] Benchmark performance under load
- Resource: Redis docs
- Expected outcome: Better caching in your API project

## Week 4: Review & Practice
- [ ] Apply learnings from Weeks 1-3 in cutie-server
- [ ] Re-scan projects to compare growth
- [ ] Write a summary of learning outcomes
"""

SAMPLE_PLAN_ZH = """# 个性化学习计划
> 生成日期：{date} | 基于你的技能画像

## 目标
提升系统设计与架构能力，聚焦实时通信可靠性和分布式系统。

## 第 1 周：WebSocket 可靠性设计
- [ ] 学习 RFC 6455 心跳机制
- [ ] 实现 cutie-server 的断线重连
- [ ] 编写断连场景的集成测试
- 资源：Socket.IO 官方文档
- 预期成果：WebSocket 断线率降低 80%

## 第 2 周：分布式可观测性
- [ ] 在一个微服务中接入 OpenTelemetry
- [ ] 添加带关联 ID 的结构化日志
- [ ] 创建 Grafana 监控面板
- 资源：OpenTelemetry 文档，Grafana 教程
- 预期成果：跨服务问题排查速度提升

## 第 3 周：Redis Cluster
- [ ] 本地部署 3 节点 Redis Cluster
- [ ] 将 cutie-server 缓存迁移到 Redis Cluster
- [ ] 压测性能表现
- 资源：Redis 文档
- 预期成果：API 项目的缓存能力提升

## 第 4 周：回顾与实践
- [ ] 在 cutie-server 中综合应用前几周所学
- [ ] 重新扫描项目，对比 growth
- [ ] 总结学习收获
"""


def _make_profile(**kwargs) -> Profile:
    defaults = {
        "persona": Persona(
            learning_goal=LearningGoal.SYSTEM_DESIGN,
            language=Language.EN,
        ),
        "skills": Skills(
            languages={
                "TypeScript": LanguageSkill(
                    level=SkillLevel.ADVANCED,
                    lines=12000,
                    frameworks=["Express", "Socket.IO"],
                    projects=["cutie-server"],
                ),
            },
            domains={
                "WebSocket": DomainSkill(
                    level=SkillLevel.PROFICIENT,
                    gaps=["reconnection logic", "heartbeat"],
                ),
            },
        ),
        "calibration": Calibration(),
    }
    defaults.update(kwargs)
    return Profile(**defaults)


def _make_provider_mock(*responses: str) -> AsyncMock:
    """Create a mock provider that returns responses in sequence.

    The first call returns recommendations JSON, the second returns the plan Markdown.
    """
    provider = AsyncMock()
    provider.chat = AsyncMock(side_effect=list(responses))
    provider.max_context_tokens = MagicMock(return_value=128_000)
    provider.name = MagicMock(return_value="mock")
    return provider


# ===========================================================================
# 1. _clean_markdown — pure function tests
# ===========================================================================


class TestCleanMarkdown:
    def test_strips_code_fences(self):
        text = "```markdown\n# Plan\n- [ ] item\n```"
        result = _clean_markdown(text)
        assert result == "# Plan\n- [ ] item"

    def test_leaves_plain_markdown_alone(self):
        text = "# Plan\n- [ ] item"
        result = _clean_markdown(text)
        assert result == "# Plan\n- [ ] item"

    def test_handles_empty_string(self):
        assert _clean_markdown("") == ""

    def test_strips_whitespace(self):
        text = "  \n# Plan\n  "
        result = _clean_markdown(text)
        assert result == "# Plan"


# ===========================================================================
# 2. generate_plan — mock LLM tests
# ===========================================================================


class TestGeneratePlanReturnsMarkdown:
    @pytest.mark.asyncio
    async def test_returns_non_empty_markdown(self):
        provider = _make_provider_mock(
            json.dumps(SAMPLE_RECOMMENDATIONS),
            SAMPLE_PLAN_EN,
        )
        profile = _make_profile()
        result = await generate_plan(profile, provider, weeks=4, language=Language.EN)
        assert result
        assert isinstance(result, str)
        assert "# " in result

    @pytest.mark.asyncio
    async def test_returns_markdown_for_zh(self):
        provider = _make_provider_mock(
            json.dumps(SAMPLE_RECOMMENDATIONS),
            SAMPLE_PLAN_ZH,
        )
        profile = _make_profile(
            persona=Persona(learning_goal=LearningGoal.SYSTEM_DESIGN, language=Language.ZH),
        )
        result = await generate_plan(profile, provider, weeks=4, language=Language.ZH)
        assert result
        assert isinstance(result, str)


class TestGeneratePlanContainsWeeks:
    @pytest.mark.asyncio
    async def test_en_plan_contains_week_headers(self):
        provider = _make_provider_mock(
            json.dumps(SAMPLE_RECOMMENDATIONS),
            SAMPLE_PLAN_EN,
        )
        profile = _make_profile()
        result = await generate_plan(profile, provider, weeks=4, language=Language.EN)
        assert "Week 1" in result or "Week 2" in result

    @pytest.mark.asyncio
    async def test_zh_plan_contains_week_headers(self):
        provider = _make_provider_mock(
            json.dumps(SAMPLE_RECOMMENDATIONS),
            SAMPLE_PLAN_ZH,
        )
        profile = _make_profile(
            persona=Persona(learning_goal=LearningGoal.SYSTEM_DESIGN, language=Language.ZH),
        )
        result = await generate_plan(profile, provider, weeks=4, language=Language.ZH)
        import re
        assert re.search(r"第.*周", result)

    @pytest.mark.asyncio
    async def test_plan_contains_checkboxes(self):
        provider = _make_provider_mock(
            json.dumps(SAMPLE_RECOMMENDATIONS),
            SAMPLE_PLAN_EN,
        )
        profile = _make_profile()
        result = await generate_plan(profile, provider, weeks=4, language=Language.EN)
        assert "- [ ]" in result


class TestGeneratePlanUsesLanguage:
    @pytest.mark.asyncio
    async def test_en_prompt_uses_english_template(self):
        provider = _make_provider_mock(
            json.dumps(SAMPLE_RECOMMENDATIONS),
            SAMPLE_PLAN_EN,
        )
        profile = _make_profile()
        await generate_plan(profile, provider, weeks=4, language=Language.EN)

        plan_call = provider.chat.call_args_list[1]
        messages = plan_call[0][0]
        user_prompt = messages[1]["content"]
        assert "You are a senior technical mentor" in user_prompt
        assert "Output in English" in user_prompt

    @pytest.mark.asyncio
    async def test_zh_prompt_uses_chinese_template(self):
        provider = _make_provider_mock(
            json.dumps(SAMPLE_RECOMMENDATIONS),
            SAMPLE_PLAN_ZH,
        )
        profile = _make_profile(
            persona=Persona(learning_goal=LearningGoal.SYSTEM_DESIGN, language=Language.ZH),
        )
        await generate_plan(profile, provider, weeks=4, language=Language.ZH)

        plan_call = provider.chat.call_args_list[1]
        messages = plan_call[0][0]
        user_prompt = messages[1]["content"]
        assert "你是一位资深技术导师" in user_prompt
        assert "用中文输出" in user_prompt


class TestGeneratePlanCallsProvider:
    @pytest.mark.asyncio
    async def test_calls_provider_twice(self):
        """First call for recommendations, second call for plan generation."""
        provider = _make_provider_mock(
            json.dumps(SAMPLE_RECOMMENDATIONS),
            SAMPLE_PLAN_EN,
        )
        profile = _make_profile()
        await generate_plan(profile, provider, weeks=4, language=Language.EN)
        assert provider.chat.await_count == 2

    @pytest.mark.asyncio
    async def test_plan_call_has_system_and_user_messages(self):
        provider = _make_provider_mock(
            json.dumps(SAMPLE_RECOMMENDATIONS),
            SAMPLE_PLAN_EN,
        )
        profile = _make_profile()
        await generate_plan(profile, provider, weeks=4, language=Language.EN)

        plan_call = provider.chat.call_args_list[1]
        messages = plan_call[0][0]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_empty_recommendations_still_generates_plan(self):
        provider = _make_provider_mock(
            "[]",
            SAMPLE_PLAN_EN,
        )
        profile = _make_profile()
        result = await generate_plan(profile, provider, weeks=4, language=Language.EN)
        assert result
        assert provider.chat.await_count == 2
