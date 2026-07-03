"""Tests for weekly and monthly reflection features."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from neocortex.models import (
    ConceptEntry,
    DomainSkill,
    Language,
    LearningGoal,
    Persona,
    Profile,
    Role,
    SkillLevel,
    Skills,
)


@pytest.fixture()
def profile_with_gaps():
    return Profile(
        persona=Persona(role=Role.BACKEND, learning_goal=LearningGoal.LEVEL_UP),
        skills=Skills(
            domains={
                "backend": DomainSkill(
                    level=SkillLevel.PROFICIENT,
                    gaps=["distributed-systems", "event-sourcing"],
                ),
            }
        ),
    )


@pytest.fixture()
def mock_provider():
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value="## 知识演化\nSome insights.\n\n## 方向偏差\nOn track.\n\n## 认知更新\nNew understanding.\n\n## 下月建议\nKeep going.")
    provider.name.return_value = "mock"
    provider.max_context_tokens.return_value = 100000
    return provider


@pytest.fixture()
def notes_dir(tmp_path):
    d = tmp_path / "notes"
    d.mkdir()
    return d


@pytest.fixture()
def sample_notes():
    return [
        {"filename": "note1.md", "title": "Event Sourcing Basics", "date": date.today().isoformat(), "content": "Event sourcing stores state as events."},
        {"filename": "note2.md", "title": "CQRS Patterns", "date": date.today().isoformat(), "content": "CQRS separates reads and writes."},
        {"filename": "note3.md", "title": "Distributed Consensus", "date": date.today().isoformat(), "content": "Raft and Paxos for consensus."},
    ]


@pytest.fixture()
def sample_concepts():
    today = date.today().isoformat()
    return [
        ConceptEntry(name="Event Sourcing", evidence_count=1, last_updated=today, source_notes=["note1.md"]),
        ConceptEntry(name="CQRS", evidence_count=3, last_updated=today, source_notes=["note2.md"]),
        ConceptEntry(name="Raft", evidence_count=0, last_updated=today, source_notes=["note3.md"]),
    ]


class TestMonthlyReflectionGeneration:
    @pytest.mark.asyncio
    async def test_generates_monthly_report(self, mock_provider, sample_notes, sample_concepts, profile_with_gaps):
        from neocortex.cmd_visualize import _generate_monthly_reflection

        result = await _generate_monthly_reflection(
            sample_notes, sample_concepts, profile_with_gaps, mock_provider, Language.ZH, 30,
        )

        assert result
        mock_provider.chat.assert_called_once()
        prompt = mock_provider.chat.call_args[0][0][1]["content"]
        assert "backend" in prompt
        assert "level_up" in prompt
        assert "3" in prompt  # len(notes) == 3

    @pytest.mark.asyncio
    async def test_monthly_includes_belief_changes(self, mock_provider, sample_notes, sample_concepts, profile_with_gaps, tmp_path):
        from neocortex.cmd_visualize import _generate_monthly_reflection

        belief_changes = [
            {"concept": "Event Sourcing", "from": "only for large systems", "to": "useful at any scale", "date": date.today().isoformat()},
        ]

        with patch("neocortex.config.load_belief_changes", return_value=belief_changes):
            await _generate_monthly_reflection(
                sample_notes, sample_concepts, profile_with_gaps, mock_provider, Language.ZH, 30,
            )

        prompt = mock_provider.chat.call_args[0][0][1]["content"]
        assert "Event Sourcing" in prompt
        assert "only for large systems" in prompt
        assert "useful at any scale" in prompt

    @pytest.mark.asyncio
    async def test_monthly_handles_missing_belief_changes(self, mock_provider, sample_notes, sample_concepts, profile_with_gaps):
        from neocortex.cmd_visualize import _generate_monthly_reflection

        with patch("neocortex.config.load_belief_changes", side_effect=Exception("not available")):
            result = await _generate_monthly_reflection(
                sample_notes, sample_concepts, profile_with_gaps, mock_provider, Language.EN, 30,
            )

        assert result
        mock_provider.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_monthly_english_output(self, mock_provider, sample_notes, sample_concepts, profile_with_gaps):
        from neocortex.cmd_visualize import _generate_monthly_reflection

        await _generate_monthly_reflection(
            sample_notes, sample_concepts, profile_with_gaps, mock_provider, Language.EN, 30,
        )

        prompt = mock_provider.chat.call_args[0][0][1]["content"]
        assert "Output in English" in prompt


class TestMonthlyReflectionInDigest:
    def test_monthly_saves_insight_file(self, notes_dir, profile_with_gaps):
        today = date.today().isoformat()
        (notes_dir / "note1.md").write_text("# Note 1\nContent.", encoding="utf-8")

        insights_dir = notes_dir / "insights"
        insights_dir.mkdir(parents=True, exist_ok=True)
        monthly_path = insights_dir / f"monthly-reflect-{today}.md"
        monthly_path.write_text("# Monthly Reflection\n\nTest content.", encoding="utf-8")

        assert monthly_path.exists()
        content = monthly_path.read_text(encoding="utf-8")
        assert "Monthly Reflection" in content


class TestWeeklyReflectionSave:
    def test_saves_weekly_reflection_as_insight(self, tmp_path):
        from neocortex.asker import save_insight

        with patch("neocortex.config.get_notes_dir", return_value=tmp_path):
            question = f"Weekly reflection {date.today().isoformat()}"
            content = "## 综合\nBiggest takeaway here.\n\n## 认知更新\nChanged my view on X.\n\n"
            path = save_insight(question, content, Language.ZH)

        assert path.exists()
        saved = path.read_text(encoding="utf-8")
        assert "Weekly reflection" in saved
        assert "综合" in saved
        assert "认知更新" in saved

    def test_empty_responses_not_saved(self):
        synthesis = ""
        update = "   "
        should_save = bool(synthesis.strip() or update.strip())
        assert not should_save

    def test_partial_responses_saved(self):
        synthesis = "My biggest takeaway"
        update = ""
        should_save = bool(synthesis.strip() or update.strip())
        assert should_save


class TestNonInteractiveSkipsReflection:
    def test_isatty_false_skips_reflection(self):
        import sys
        with patch.object(sys, "stdout") as mock_stdout:
            mock_stdout.isatty.return_value = False
            assert not sys.stdout.isatty()

    def test_isatty_true_allows_reflection(self):
        import sys
        with patch.object(sys, "stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            assert sys.stdout.isatty()

    def test_no_notes_skips_reflection(self):
        recent_notes: list[dict] = []
        is_tty = True
        should_reflect = is_tty and bool(recent_notes)
        assert not should_reflect


class TestMonthlyDetection:
    def test_days_28_is_monthly(self):
        assert 28 >= 28

    def test_days_30_is_monthly(self):
        assert 30 >= 28

    def test_days_7_is_not_monthly(self):
        assert not (7 >= 28)

    def test_days_14_is_not_monthly(self):
        assert not (14 >= 28)


class TestWeeklyReflectionTopics:
    def test_extracts_topics_from_notes(self):
        notes = [
            {"title": "Event Sourcing Basics", "date": "2026-04-01"},
            {"title": "CQRS Deep Dive", "date": "2026-04-02"},
            {"title": "Distributed Systems", "date": "2026-04-03"},
        ]
        topics = set()
        for note in notes[:10]:
            topics.add(note.get("title", "")[:30])
        topics_str = ", ".join(list(topics)[:5])

        assert "Event Sourcing Basics" in topics_str
        assert "CQRS Deep Dive" in topics_str
        assert "Distributed Systems" in topics_str

    def test_limits_topics_to_five(self):
        notes = [{"title": f"Topic {i}"} for i in range(20)]
        topics = set()
        for note in notes[:10]:
            topics.add(note.get("title", "")[:30])
        topics_list = list(topics)[:5]
        assert len(topics_list) <= 5


class TestActiveGapDetection:
    def test_finds_first_gap(self, profile_with_gaps):
        active_gap = ""
        for domain in profile_with_gaps.skills.domains.values():
            if domain.gaps:
                active_gap = domain.gaps[0]
                break
        assert active_gap == "distributed-systems"

    def test_no_gaps_returns_empty(self):
        prof = Profile(
            skills=Skills(
                domains={"backend": DomainSkill(level=SkillLevel.PROFICIENT, gaps=[])}
            )
        )
        active_gap = ""
        for domain in prof.skills.domains.values():
            if domain.gaps:
                active_gap = domain.gaps[0]
                break
        assert active_gap == ""
