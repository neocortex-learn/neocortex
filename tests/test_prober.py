"""Tests for Socratic Probe — skill verification and confidence tracking."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from neocortex.models import (
    DomainSkill,
    IntegrationSkill,
    LanguageSkill,
    Profile,
    Skills,
    SkillLevel,
)
from neocortex.prober import (
    evaluate_response,
    generate_probe,
    get_low_confidence_skills,
    update_skill_confidence,
)


class TestGetLowConfidenceSkills:
    def test_finds_low_confidence(self):
        prof = Profile(skills=Skills(
            languages={"python": LanguageSkill(level=SkillLevel.ADVANCED, confidence=0.3)},
            domains={"testing": DomainSkill(level=SkillLevel.BEGINNER, confidence=0.8)},
        ))
        low = get_low_confidence_skills(prof, threshold=0.5)
        assert len(low) == 1
        assert low[0]["name"] == "python"
        assert low[0]["confidence"] == 0.3

    def test_all_above_threshold(self):
        prof = Profile(skills=Skills(
            languages={"python": LanguageSkill(confidence=0.9)},
        ))
        assert get_low_confidence_skills(prof, threshold=0.5) == []

    def test_sorted_by_confidence(self):
        prof = Profile(skills=Skills(
            languages={"python": LanguageSkill(confidence=0.4)},
            domains={"testing": DomainSkill(confidence=0.2)},
            integrations={"redis": IntegrationSkill(confidence=0.1)},
        ))
        low = get_low_confidence_skills(prof, threshold=0.5)
        assert len(low) == 3
        assert low[0]["name"] == "redis"  # lowest first
        assert low[1]["name"] == "testing"
        assert low[2]["name"] == "python"

    def test_empty_profile(self):
        assert get_low_confidence_skills(Profile()) == []

    def test_includes_all_skill_types(self):
        from neocortex.models import ArchitectureSkill
        prof = Profile(skills=Skills(
            languages={"py": LanguageSkill(confidence=0.1)},
            domains={"db": DomainSkill(confidence=0.1)},
            integrations={"aws": IntegrationSkill(confidence=0.1)},
            architecture={"micro": ArchitectureSkill(confidence=0.1)},
        ))
        low = get_low_confidence_skills(prof, threshold=0.5)
        assert len(low) == 4


class TestUpdateSkillConfidence:
    def test_increases_confidence(self):
        prof = Profile(skills=Skills(
            domains={"testing": DomainSkill(confidence=0.3)},
        ))
        new = update_skill_confidence(prof, "testing", "domain", 0.2)
        assert new == pytest.approx(0.5)
        assert prof.skills.domains["testing"].confidence == pytest.approx(0.5)
        assert prof.skills.domains["testing"].last_verified is not None

    def test_decreases_confidence(self):
        prof = Profile(skills=Skills(
            languages={"python": LanguageSkill(confidence=0.5)},
        ))
        new = update_skill_confidence(prof, "python", "language", -0.3)
        assert new == pytest.approx(0.2)

    def test_clamps_to_0_1(self):
        prof = Profile(skills=Skills(
            domains={"testing": DomainSkill(confidence=0.9)},
        ))
        new = update_skill_confidence(prof, "testing", "domain", 0.5)
        assert new == 1.0

        prof.skills.domains["testing"].confidence = 0.1
        new = update_skill_confidence(prof, "testing", "domain", -0.5)
        assert new == 0.0

    def test_unknown_skill_returns_default(self):
        prof = Profile()
        new = update_skill_confidence(prof, "nonexistent", "domain", 0.5)
        assert new == 0.3


class TestGenerateProbe:
    @pytest.mark.asyncio
    async def test_returns_questions(self):
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=json.dumps({
            "questions": ["What happens if Redis connection drops?", "Why use Redis over Memcached?"],
            "context": "Found Redis caching in your project",
        }))

        prof = Profile(skills=Skills(
            languages={"python": LanguageSkill(projects=["myapp"])},
        ))
        result = await generate_probe("redis", "integration", "proficient", prof, provider)
        assert len(result["questions"]) == 2
        assert result["context"]

    @pytest.mark.asyncio
    async def test_handles_bad_json(self):
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value="not json at all")

        prof = Profile()
        result = await generate_probe("redis", "integration", "beginner", prof, provider)
        assert result["questions"] == []

    @pytest.mark.asyncio
    async def test_limits_to_2_questions(self):
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=json.dumps({
            "questions": ["q1", "q2", "q3", "q4"],
            "context": "too many",
        }))

        prof = Profile()
        result = await generate_probe("redis", "integration", "beginner", prof, provider)
        assert len(result["questions"]) <= 2


class TestEvaluateResponse:
    @pytest.mark.asyncio
    async def test_evaluates_good_answer(self):
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=json.dumps({
            "understanding": "solid",
            "confidence_delta": 0.15,
            "feedback": "Good understanding of Redis cache invalidation.",
        }))

        result = await evaluate_response("redis", "q?", "detailed answer", "proficient", provider)
        assert result["understanding"] == "solid"
        assert result["confidence_delta"] == pytest.approx(0.15)

    @pytest.mark.asyncio
    async def test_evaluates_bad_answer(self):
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=json.dumps({
            "understanding": "none",
            "confidence_delta": -0.3,
            "feedback": "Could not explain basic concepts.",
        }))

        result = await evaluate_response("redis", "q?", "i dont know", "advanced", provider)
        assert result["understanding"] == "none"
        assert result["confidence_delta"] == pytest.approx(-0.3)

    @pytest.mark.asyncio
    async def test_clamps_delta(self):
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=json.dumps({
            "understanding": "deep",
            "confidence_delta": 0.9,
            "feedback": "Exceptional.",
        }))

        result = await evaluate_response("redis", "q?", "answer", "beginner", provider)
        assert result["confidence_delta"] <= 0.3

    @pytest.mark.asyncio
    async def test_handles_bad_json(self):
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value="broken")

        result = await evaluate_response("redis", "q?", "answer", "beginner", provider)
        assert result["understanding"] == "surface"
        assert result["confidence_delta"] == 0.0


class TestConfidenceDefaults:
    def test_new_skills_have_low_confidence(self):
        skill = LanguageSkill(level=SkillLevel.ADVANCED)
        assert skill.confidence == 0.3

    def test_backward_compatible(self):
        """Old profiles without confidence field should still load."""
        data = {"level": "advanced", "lines": 500, "frameworks": ["flask"]}
        skill = LanguageSkill(**data)
        assert skill.confidence == 0.3
        assert skill.last_verified is None
