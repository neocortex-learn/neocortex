"""Tests for closed-loop learning — models, config persistence, gap tracking, resource parsing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from neocortex.models import (
    DomainSkill,
    GapProgress,
    IntegrationSkill,
    Profile,
    RecommendationRecord,
    Resource,
    Skills,
    SkillLevel,
)
from neocortex.recommender import _extract_gaps, _build_context, parse_resource


# ── Resource parsing ──


class TestParseResource:
    def test_title_and_url(self):
        r = parse_resource("Pytest Best Practices -- https://docs.pytest.org/en/latest/")
        assert r.title == "Pytest Best Practices"
        assert r.url == "https://docs.pytest.org/en/latest/"

    def test_url_only(self):
        r = parse_resource("https://docs.pytest.org")
        assert r.title == "https://docs.pytest.org"
        assert r.url == "https://docs.pytest.org"

    def test_title_only(self):
        r = parse_resource("Clean Code by Robert Martin")
        assert r.title == "Clean Code by Robert Martin"
        assert r.url == ""

    def test_chinese_separator(self):
        r = parse_resource("Pytest 教程：https://docs.pytest.org")
        assert r.url == "https://docs.pytest.org"
        assert "Pytest" in r.title

    def test_dash_separator(self):
        r = parse_resource("Official docs - https://example.com/docs")
        assert r.url == "https://example.com/docs"
        assert r.title == "Official docs"

    def test_empty_string(self):
        r = parse_resource("")
        assert r.title == ""
        assert r.url == ""


# ── Gap extraction ──


class TestExtractGaps:
    def test_extracts_domain_gaps(self):
        prof = Profile(skills=Skills(domains={
            "testing": DomainSkill(level=SkillLevel.BEGINNER, gaps=["pytest", "coverage"]),
            "databases": DomainSkill(level=SkillLevel.PROFICIENT, gaps=["indexing"]),
        }))
        gaps = _extract_gaps(prof)
        gap_names = [g["gap"] for g in gaps]
        assert "pytest" in gap_names
        assert "coverage" in gap_names
        assert "indexing" in gap_names
        assert len(gaps) == 3

    def test_extracts_integration_gaps(self):
        prof = Profile(skills=Skills(integrations={
            "cloud": IntegrationSkill(level=SkillLevel.BEGINNER, gaps=["docker_compose"]),
        }))
        gaps = _extract_gaps(prof)
        assert len(gaps) == 1
        assert gaps[0]["gap"] == "docker_compose"

    def test_empty_profile(self):
        prof = Profile()
        gaps = _extract_gaps(prof)
        assert gaps == []


# ── Context building ──


class TestBuildContext:
    def test_includes_gaps(self):
        prof = Profile(skills=Skills(domains={
            "testing": DomainSkill(level=SkillLevel.BEGINNER, gaps=["pytest"]),
        }))
        ctx = _build_context(prof, [])
        assert "pytest" in ctx

    def test_includes_completed_recs(self):
        prof = Profile()
        recs = [RecommendationRecord(
            id="1", topic="Docker", status="completed", created_at="2026-03-21",
        )]
        ctx = _build_context(prof, recs)
        assert "Docker" in ctx

    def test_handles_empty(self):
        ctx = _build_context(Profile(), [])
        assert isinstance(ctx, str)


# ── Config persistence ──


class TestConfigPersistence:
    def test_recommendations_roundtrip(self, tmp_path: Path):
        from neocortex.config import load_recommendations, save_recommendations

        recs = [RecommendationRecord(
            id="test-1",
            topic="pytest",
            resources=[Resource(title="docs", url="https://docs.pytest.org")],
            related_gaps=["testing"],
            created_at="2026-03-21",
        )]

        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            save_recommendations(recs)
            loaded = load_recommendations()
            assert len(loaded) == 1
            assert loaded[0].topic == "pytest"
            assert loaded[0].resources[0].url == "https://docs.pytest.org"

    def test_recommendations_filter_by_status(self, tmp_path: Path):
        from neocortex.config import load_recommendations, save_recommendations

        recs = [
            RecommendationRecord(id="1", topic="a", status="pending", created_at="2026-03-21"),
            RecommendationRecord(id="2", topic="b", status="completed", created_at="2026-03-20"),
        ]

        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            save_recommendations(recs)
            pending = load_recommendations(status="pending")
            assert len(pending) == 1
            assert pending[0].topic == "a"

    def test_gap_progress_roundtrip(self, tmp_path: Path):
        from neocortex.config import load_gap_progress, save_gap_progress

        progress = {
            "pytest": GapProgress(status="learning", reads=1, first_seen="2026-03-21", last_read="2026-03-21"),
        }

        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            save_gap_progress(progress)
            loaded = load_gap_progress()
            assert loaded["pytest"].status == "learning"
            assert loaded["pytest"].reads == 1

    def test_load_missing_file(self, tmp_path: Path):
        from neocortex.config import load_recommendations, load_gap_progress

        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            assert load_recommendations() == []
            assert load_gap_progress() == {}

    def test_load_corrupt_json(self, tmp_path: Path):
        from neocortex.config import load_recommendations

        (tmp_path / "recommendations.json").write_text("not json", encoding="utf-8")
        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            assert load_recommendations() == []


# ── Gap status transitions ──


class TestUpdateGapStatus:
    def test_gap_to_learning(self, tmp_path: Path):
        from neocortex.config import update_gap_status, load_gap_progress

        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            prof = Profile(skills=Skills(domains={
                "testing": DomainSkill(gaps=["pytest_fixtures"]),
            }))
            status = update_gap_status("pytest_fixtures", prof)
            assert status == "learning"

            progress = load_gap_progress()
            assert progress["pytest_fixtures"].reads == 1

    def test_synonym_normalized_in_progress(self, tmp_path: Path):
        from neocortex.config import update_gap_status, load_gap_progress

        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            prof = Profile(skills=Skills(domains={
                "testing": DomainSkill(gaps=["testing"]),
            }))
            # "pytest" normalizes to "testing"
            status = update_gap_status("pytest", prof)
            assert status == "learning"
            progress = load_gap_progress()
            assert "testing" in progress

    def test_learning_stays_until_3_reads(self, tmp_path: Path):
        from neocortex.config import update_gap_status, save_gap_progress

        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            save_gap_progress({
                "pytest_fixtures": GapProgress(status="learning", reads=1, first_seen="2026-03-21"),
            })
            prof = Profile(skills=Skills(domains={"testing": DomainSkill(gaps=["pytest_fixtures"])}))
            status = update_gap_status("pytest_fixtures", prof)
            assert status == "learning"

    def test_learning_to_known_at_3_reads(self, tmp_path: Path):
        from neocortex.config import update_gap_status, save_gap_progress

        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            save_gap_progress({
                "pytest_fixtures": GapProgress(status="learning", reads=2, first_seen="2026-03-21"),
            })
            prof = Profile(skills=Skills(domains={"testing": DomainSkill(gaps=["pytest_fixtures"])}))
            status = update_gap_status("pytest_fixtures", prof)
            assert status == "known"
            assert "pytest_fixtures" not in prof.skills.domains["testing"].gaps

    def test_known_is_noop(self, tmp_path: Path):
        from neocortex.config import update_gap_status, save_gap_progress

        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            save_gap_progress({
                "pytest_fixtures": GapProgress(status="known", reads=5, first_seen="2026-03-21"),
            })
            prof = Profile()
            status = update_gap_status("pytest_fixtures", prof)
            assert status == "known"


# ── Filter known gaps ──


class TestFilterKnownGaps:
    def test_removes_known_gaps_from_profile(self, tmp_path: Path):
        from neocortex.config import filter_known_gaps, save_gap_progress

        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            save_gap_progress({
                "pytest": GapProgress(status="known", reads=3, first_seen="2026-03-21"),
                "docker": GapProgress(status="learning", reads=1, first_seen="2026-03-21"),
            })
            prof = Profile(skills=Skills(domains={
                "testing": DomainSkill(gaps=["pytest", "coverage"]),
            }))
            filter_known_gaps(prof)
            assert "pytest" not in prof.skills.domains["testing"].gaps
            assert "coverage" in prof.skills.domains["testing"].gaps

    def test_no_progress_file(self, tmp_path: Path):
        from neocortex.config import filter_known_gaps

        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            prof = Profile(skills=Skills(domains={
                "testing": DomainSkill(gaps=["pytest"]),
            }))
            filter_known_gaps(prof)
            assert "pytest" in prof.skills.domains["testing"].gaps
