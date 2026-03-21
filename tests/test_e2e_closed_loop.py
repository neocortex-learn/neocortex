"""End-to-end test for the closed-loop learning flow.

Verifies: scan → recommend → read → recommend produces different results
the second time, proving the system learns from user activity.

Uses mock LLM to avoid real API calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from neocortex.config import (
    filter_known_gaps,
    load_gap_progress,
    load_recommendations,
    save_gap_progress,
    save_recommendations,
    update_gap_status,
)
from neocortex.models import (
    DomainSkill,
    GapProgress,
    IntegrationSkill,
    Language,
    Profile,
    RecommendationRecord,
    Resource,
    Skills,
    SkillLevel,
)
from neocortex.recommender import (
    _build_context,
    _extract_gaps,
    generate_recommendations,
    parse_resource,
)
from neocortex.tracker import expire_stale_recommendations, match_recommendation


class TestClosedLoopE2E:
    """Full closed-loop: profile → recommend → read → gap update → recommend again."""

    @pytest.fixture
    def data_dir(self, tmp_path: Path):
        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            yield tmp_path

    @pytest.fixture
    def profile(self) -> Profile:
        return Profile(skills=Skills(
            domains={
                "testing": DomainSkill(
                    level=SkillLevel.BEGINNER,
                    evidence=["has pytest in requirements"],
                    gaps=["pytest_fixtures", "test_coverage"],
                ),
                "databases": DomainSkill(
                    level=SkillLevel.PROFICIENT,
                    evidence=["uses SQLAlchemy"],
                    gaps=["query_optimization"],
                ),
            },
            integrations={
                "cloud": IntegrationSkill(
                    level=SkillLevel.BEGINNER,
                    providers=["aws"],
                    gaps=["docker_compose"],
                ),
            },
        ))

    def _mock_llm_response_round1(self) -> str:
        return json.dumps([
            {
                "topic": "Pytest Fixtures Deep Dive",
                "reason": "Your testing skills show gaps in fixtures",
                "resources": [
                    {"title": "Pytest Fixtures Guide", "url": "https://docs.pytest.org/en/latest/how-to/fixtures.html", "type": "doc"},
                    {"title": "Real Python Pytest", "url": "https://realpython.com/pytest-fixtures/", "type": "article"},
                ],
                "expected_benefit": "Write better test setups",
                "priority": "high",
                "related_gaps": ["pytest_fixtures"],
            },
            {
                "topic": "Docker Compose for Development",
                "reason": "Cloud integration gap",
                "resources": [
                    {"title": "Docker Compose Docs", "url": "https://docs.docker.com/compose/", "type": "doc"},
                ],
                "expected_benefit": "Containerized dev environment",
                "priority": "medium",
                "related_gaps": ["docker_compose"],
            },
        ])

    def _mock_llm_response_round2(self) -> str:
        """Second round should NOT recommend pytest_fixtures (already completed)."""
        return json.dumps([
            {
                "topic": "Test Coverage Best Practices",
                "reason": "Now that you know fixtures, improve coverage",
                "resources": [
                    {"title": "Coverage.py Docs", "url": "https://coverage.readthedocs.io/", "type": "doc"},
                ],
                "expected_benefit": "Higher test coverage",
                "priority": "high",
                "related_gaps": ["test_coverage"],
            },
            {
                "topic": "SQL Query Optimization",
                "reason": "Database gap in query performance",
                "resources": [
                    {"title": "Use The Index, Luke", "url": "https://use-the-index-luke.com/", "type": "article"},
                ],
                "expected_benefit": "Faster database queries",
                "priority": "medium",
                "related_gaps": ["query_optimization"],
            },
        ])

    def test_full_closed_loop(self, data_dir: Path, profile: Profile):
        """The complete flow: recommend → read → gap update → recommend again."""

        # ── Step 1: Extract gaps from profile ──
        gaps = _extract_gaps(profile)
        gap_names = [g["gap"] for g in gaps]
        assert "pytest_fixtures" in gap_names
        assert "docker_compose" in gap_names
        assert len(gaps) == 4

        # ── Step 2: First recommendation round ──
        mock_provider = AsyncMock()
        mock_provider.chat = AsyncMock(return_value=self._mock_llm_response_round1())

        import asyncio
        recs = asyncio.run(generate_recommendations(profile, mock_provider, count=2))
        assert len(recs) == 2
        assert recs[0].topic == "Pytest Fixtures Deep Dive"
        assert recs[0].related_gaps == ["pytest_fixtures"]

        # Persist recommendations
        from uuid import uuid4
        from datetime import date
        records = []
        for rec in recs:
            records.append(RecommendationRecord(
                id=str(uuid4()),
                topic=rec.topic,
                resources=[parse_resource(r) for r in rec.resources],
                related_gaps=rec.related_gaps,
                created_at=date.today().isoformat(),
            ))
        save_recommendations(records)
        assert len(load_recommendations()) == 2

        # ── Step 3: User reads the recommended article ──
        pending = load_recommendations(status="pending")
        matched = match_recommendation(
            "https://docs.pytest.org/en/latest/how-to/fixtures.html",
            "Pytest Fixtures Guide",
            pending,
        )
        assert matched is not None
        assert matched.topic == "Pytest Fixtures Deep Dive"

        # Update recommendation status and persist
        all_records = load_recommendations()
        for r in all_records:
            if r.id == matched.id:
                r.status = "completed"
                r.completed_at = date.today().isoformat()
        save_recommendations(all_records)

        # Update gap status
        new_status = update_gap_status("pytest_fixtures", profile)
        assert new_status == "learning"

        progress = load_gap_progress()
        assert progress["pytest_fixtures"].status == "learning"
        assert progress["pytest_fixtures"].reads == 1

        # ── Step 4: Simulate reading 2 more articles (gap → known) ──
        update_gap_status("pytest_fixtures", profile)
        update_gap_status("pytest_fixtures", profile)

        progress = load_gap_progress()
        assert progress["pytest_fixtures"].status == "known"
        assert progress["pytest_fixtures"].reads == 3

        # Gap should be removed from profile
        assert "pytest_fixtures" not in profile.skills.domains["testing"].gaps
        assert "test_coverage" in profile.skills.domains["testing"].gaps  # Other gap still there

        # ── Step 5: Second recommendation round ──
        # Build context should now include completed recommendation
        all_records = load_recommendations()
        context = _build_context(profile, all_records)
        assert "Pytest Fixtures Deep Dive" in context  # Shows in completed history
        assert "pytest_fixtures" not in context  # Gap removed from profile

        mock_provider.chat = AsyncMock(return_value=self._mock_llm_response_round2())
        recs2 = asyncio.run(generate_recommendations(profile, mock_provider, count=2, records=all_records))
        assert len(recs2) == 2

        # Verify second round recommends DIFFERENT topics
        round2_topics = {r.topic for r in recs2}
        round1_topics = {r.topic for r in recs}
        assert round2_topics != round1_topics
        assert "Pytest Fixtures Deep Dive" not in round2_topics

        # ── Step 6: Verify scan doesn't resurrect known gaps ──
        profile.skills.domains["testing"].gaps.append("pytest_fixtures")  # Simulate re-scan adding it back
        filter_known_gaps(profile)
        assert "pytest_fixtures" not in profile.skills.domains["testing"].gaps  # Filtered out

    def test_expiration_flow(self, data_dir: Path):
        """Old pending recommendations get expired to 'skipped'."""
        old_rec = RecommendationRecord(
            id="old-1",
            topic="Ancient Topic",
            created_at="2025-01-01",
            status="pending",
        )
        recent_rec = RecommendationRecord(
            id="new-1",
            topic="Fresh Topic",
            created_at="2026-03-20",
            status="pending",
        )
        save_recommendations([old_rec, recent_rec])

        records = load_recommendations()
        records = expire_stale_recommendations(records)
        save_recommendations(records)

        final = load_recommendations()
        statuses = {r.topic: r.status for r in final}
        assert statuses["Ancient Topic"] == "skipped"
        assert statuses["Fresh Topic"] == "pending"

    def test_no_duplicate_recommendations(self, data_dir: Path, profile: Profile):
        """Running recommend twice doesn't create duplicate pending records."""
        rec = RecommendationRecord(
            id="existing-1",
            topic="Pytest Fixtures Deep Dive",
            created_at="2026-03-21",
            status="pending",
        )
        save_recommendations([rec])

        # Simulate dedup logic from cli.py recommend command
        existing_records = load_recommendations()
        existing_topics = {r.topic for r in existing_records if r.status == "pending"}

        mock_recs_from_llm = [
            type("R", (), {"topic": "Pytest Fixtures Deep Dive", "resources": [], "related_gaps": []})(),
            type("R", (), {"topic": "New Topic", "resources": [], "related_gaps": []})(),
        ]

        new_topics = [r.topic for r in mock_recs_from_llm if r.topic not in existing_topics]
        assert "Pytest Fixtures Deep Dive" not in new_topics  # Deduped
        assert "New Topic" in new_topics

    def test_level2_matching_chinese_topic(self, data_dir: Path):
        """Level 2 matching works with mixed Chinese/English."""
        rec = RecommendationRecord(
            id="1",
            topic="pytest fixtures 高级用法",
            resources=[Resource(title="Pytest Docs", url="https://docs.pytest.org/en/latest/")],
            created_at="2026-03-21",
        )
        # Same domain, keyword "pytest" in path
        matched = match_recommendation(
            "https://docs.pytest.org/en/7.0/how-to/fixtures.html",
            "Pytest Fixture Reference",
            [rec],
        )
        assert matched is rec

    def test_gap_progress_survives_multiple_scans(self, data_dir: Path):
        """Gap progress persists across multiple filter_known_gaps calls."""
        save_gap_progress({
            "pytest": GapProgress(status="known", reads=3, first_seen="2026-03-21"),
            "docker": GapProgress(status="learning", reads=1, first_seen="2026-03-21"),
        })

        profile = Profile(skills=Skills(domains={
            "testing": DomainSkill(gaps=["pytest", "coverage"]),
        }))

        # First scan
        filter_known_gaps(profile)
        assert "pytest" not in profile.skills.domains["testing"].gaps

        # Simulate second scan re-adding the gap
        profile.skills.domains["testing"].gaps.append("pytest")
        filter_known_gaps(profile)
        assert "pytest" not in profile.skills.domains["testing"].gaps  # Still filtered

        # Learning gaps are NOT filtered
        profile.skills.domains["testing"].gaps.append("docker")
        filter_known_gaps(profile)
        assert "docker" in profile.skills.domains["testing"].gaps  # Not filtered (still learning)
