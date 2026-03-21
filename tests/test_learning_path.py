"""Tests for learning path features — ordered steps, dependencies, auto-unlock."""

from __future__ import annotations

from neocortex.models import Recommendation, RecommendationRecord
from neocortex.tracker import get_unlocked_recommendations


class TestRecommendationDependencies:
    def test_step_and_depends_on_defaults(self):
        rec = Recommendation(topic="test", reason="r")
        assert rec.step == 0
        assert rec.depends_on == []

    def test_step_and_depends_on_set(self):
        rec = Recommendation(topic="test", reason="r", step=2, depends_on=["basics"])
        assert rec.step == 2
        assert rec.depends_on == ["basics"]

    def test_record_step_and_depends_on(self):
        rec = RecommendationRecord(id="1", topic="t", step=3, depends_on=["a", "b"], created_at="2026-03-21")
        assert rec.step == 3
        assert rec.depends_on == ["a", "b"]


class TestGetUnlockedRecommendations:
    def _rec(self, topic: str, depends_on: list[str] | None = None) -> RecommendationRecord:
        return RecommendationRecord(
            id=f"id-{topic}",
            topic=topic,
            depends_on=depends_on or [],
            created_at="2026-03-21",
        )

    def test_no_dependencies_all_unlocked(self):
        pending = [self._rec("A"), self._rec("B")]
        result = get_unlocked_recommendations(pending, set())
        assert len(result) == 2

    def test_unmet_dependency_locked(self):
        pending = [
            self._rec("Basics"),
            self._rec("Advanced", depends_on=["Basics"]),
        ]
        result = get_unlocked_recommendations(pending, set())
        assert len(result) == 1
        assert result[0].topic == "Basics"

    def test_met_dependency_unlocked(self):
        pending = [
            self._rec("Advanced", depends_on=["Basics"]),
        ]
        result = get_unlocked_recommendations(pending, {"Basics"})
        assert len(result) == 1
        assert result[0].topic == "Advanced"

    def test_partial_dependencies_locked(self):
        pending = [
            self._rec("Expert", depends_on=["Basics", "Intermediate"]),
        ]
        result = get_unlocked_recommendations(pending, {"Basics"})
        assert len(result) == 0

    def test_all_dependencies_met(self):
        pending = [
            self._rec("Expert", depends_on=["Basics", "Intermediate"]),
        ]
        result = get_unlocked_recommendations(pending, {"Basics", "Intermediate"})
        assert len(result) == 1

    def test_chain_unlock(self):
        """Simulate step-by-step unlocking: A → B → C."""
        a = self._rec("A")
        b = self._rec("B", depends_on=["A"])
        c = self._rec("C", depends_on=["B"])
        all_pending = [a, b, c]

        # Initially only A is unlocked
        r1 = get_unlocked_recommendations(all_pending, set())
        assert [r.topic for r in r1] == ["A"]

        # After completing A, B unlocks
        r2 = get_unlocked_recommendations(all_pending, {"A"})
        assert "A" in [r.topic for r in r2]
        assert "B" in [r.topic for r in r2]
        assert "C" not in [r.topic for r in r2]

        # After completing A+B, C unlocks
        r3 = get_unlocked_recommendations(all_pending, {"A", "B"})
        assert len(r3) == 3

    def test_empty_pending(self):
        result = get_unlocked_recommendations([], {"A"})
        assert result == []


class TestParseRecommendationsWithPath:
    def test_step_extracted(self):
        from neocortex.recommender import _parse_recommendations
        import json

        data = json.dumps([
            {"topic": "Basics", "reason": "r", "step": 1, "depends_on": []},
            {"topic": "Advanced", "reason": "r", "step": 2, "depends_on": ["Basics"]},
        ])
        recs = _parse_recommendations(data, 5)
        assert recs[0].step == 1
        assert recs[0].depends_on == []
        assert recs[1].step == 2
        assert recs[1].depends_on == ["Basics"]

    def test_step_defaults_to_index(self):
        from neocortex.recommender import _parse_recommendations
        import json

        data = json.dumps([
            {"topic": "A", "reason": "r"},
            {"topic": "B", "reason": "r"},
        ])
        recs = _parse_recommendations(data, 5)
        assert recs[0].step == 1
        assert recs[1].step == 2
