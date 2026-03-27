"""Tests for the matcher package — skill vector building, scoring, and GitHub search."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from neocortex.matcher.base import build_skill_vector, score_opportunity
from neocortex.models import (
    LanguageSkill,
    DomainSkill,
    IntegrationSkill,
    ArchitectureSkill,
    Profile,
    Skills,
    SkillLevel,
)


# ── Fixtures ──

def _make_profile(**kwargs) -> Profile:
    skills = Skills(**kwargs)
    return Profile(skills=skills)


# ── build_skill_vector tests ──

def test_build_skill_vector_empty():
    prof = _make_profile()
    vec = build_skill_vector(prof)
    assert vec == {}


def test_build_skill_vector_languages():
    prof = _make_profile(languages={
        "Python": LanguageSkill(level=SkillLevel.ADVANCED, lines=5000),
        "JavaScript": LanguageSkill(level=SkillLevel.BEGINNER, lines=200),
    })
    vec = build_skill_vector(prof)
    assert vec["python"] == 0.75
    assert vec["javascript"] == 0.25


def test_build_skill_vector_frameworks():
    prof = _make_profile(languages={
        "Python": LanguageSkill(
            level=SkillLevel.EXPERT,
            lines=10000,
            frameworks=["FastAPI", "Django"],
        ),
    })
    vec = build_skill_vector(prof)
    assert vec["python"] == 1.0
    assert vec["fastapi"] == pytest.approx(0.8)
    assert vec["django"] == pytest.approx(0.8)


def test_build_skill_vector_domains():
    prof = _make_profile(domains={
        "web-development": DomainSkill(level=SkillLevel.PROFICIENT),
    })
    vec = build_skill_vector(prof)
    assert vec["web-development"] == 0.5


def test_build_skill_vector_integrations():
    prof = _make_profile(integrations={
        "PostgreSQL": IntegrationSkill(level=SkillLevel.ADVANCED),
    })
    vec = build_skill_vector(prof)
    assert vec["postgresql"] == 0.75


def test_build_skill_vector_architecture():
    prof = _make_profile(architecture={
        "microservices": ArchitectureSkill(level=SkillLevel.EXPERT),
    })
    vec = build_skill_vector(prof)
    assert vec["microservices"] == 1.0


# ── score_opportunity tests ──

def test_score_opportunity_empty_required():
    score, matched, missing = score_opportunity({"python": 0.75}, [])
    assert score == 0.0
    assert matched == []
    assert missing == []


def test_score_opportunity_all_matched():
    vec = {"python": 0.75, "fastapi": 0.6}
    score, matched, missing = score_opportunity(vec, ["Python", "FastAPI"])
    assert score > 0
    assert "Python" in matched
    assert "FastAPI" in matched
    assert missing == []


def test_score_opportunity_partial_match():
    vec = {"python": 0.75}
    score, matched, missing = score_opportunity(vec, ["Python", "Rust"])
    assert "Python" in matched
    assert "Rust" in missing
    assert 0 < score < 1.0


def test_score_opportunity_no_match():
    vec = {"python": 0.75}
    score, matched, missing = score_opportunity(vec, ["Go", "Rust"])
    assert score == 0.0
    assert matched == []
    assert set(missing) == {"Go", "Rust"}


def test_score_opportunity_case_insensitive():
    vec = {"python": 0.5}
    score, matched, missing = score_opportunity(vec, ["PYTHON"])
    assert "PYTHON" in matched
    assert score == 0.5


# ── GitHub search tests (mocked) ──

@pytest.mark.asyncio
async def test_find_oss_opportunities_mocked():
    from neocortex.matcher.github import find_oss_opportunities

    gh_output = json.dumps([
        {
            "title": "Fix typo in docs",
            "url": "https://github.com/org/repo/issues/1",
            "repository": {"name": "repo", "nameWithOwner": "org/repo"},
            "labels": [{"name": "good first issue"}],
            "updatedAt": "2026-03-01",
        },
        {
            "title": "Add type hints",
            "url": "https://github.com/org/repo/issues/2",
            "repository": {"name": "repo", "nameWithOwner": "org/repo"},
            "labels": [{"name": "good first issue"}, {"name": "medium"}],
            "updatedAt": "2026-03-02",
        },
    ])

    mock_search = MagicMock()
    mock_search.returncode = 0
    mock_search.stdout = gh_output

    mock_topics = MagicMock()
    mock_topics.returncode = 0
    mock_topics.stdout = "python\nfastapi\n"

    prof = _make_profile(languages={
        "Python": LanguageSkill(level=SkillLevel.ADVANCED, lines=5000),
    })

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [mock_search, mock_topics, mock_topics]
        results = await find_oss_opportunities(prof, max_results=5)

    assert len(results) > 0
    for opp in results:
        assert opp.source == "github"
        assert opp.type == "oss"
        assert opp.url.startswith("https://")


@pytest.mark.asyncio
async def test_find_oss_opportunities_gh_failure():
    from neocortex.matcher.github import find_oss_opportunities

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""

    prof = _make_profile(languages={
        "Python": LanguageSkill(level=SkillLevel.ADVANCED, lines=5000),
    })

    with patch("subprocess.run", return_value=mock_result):
        results = await find_oss_opportunities(prof, max_results=5)

    assert results == []


@pytest.mark.asyncio
async def test_find_oss_opportunities_timeout():
    import subprocess as sp
    from neocortex.matcher.github import find_oss_opportunities

    prof = _make_profile(languages={
        "Python": LanguageSkill(level=SkillLevel.ADVANCED, lines=5000),
    })

    with patch("subprocess.run", side_effect=sp.TimeoutExpired("gh", 30)):
        results = await find_oss_opportunities(prof, max_results=5)

    assert results == []
