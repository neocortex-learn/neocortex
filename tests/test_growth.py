"""Tests for the skill growth tracking module."""

from __future__ import annotations

from neocortex.growth import save_snapshot, load_snapshots, compute_diff
from neocortex.models import (
    Profile, ProfileSnapshot, Skills,
    LanguageSkill, DomainSkill, SkillLevel,
)


class TestSaveAndLoadSnapshots:
    def test_save_creates_file(self, tmp_path):
        prof = Profile(skills=Skills(
            languages={"Python": LanguageSkill(level=SkillLevel.EXPERT, lines=5000, projects=["proj1"])},
        ))
        save_snapshot(prof, tmp_path, notes_count=3)
        snapshots = load_snapshots(tmp_path)
        assert len(snapshots) == 1
        assert snapshots[0].total_lines == 5000
        assert snapshots[0].total_projects == 1
        assert snapshots[0].notes_count == 3

    def test_same_day_overwrites(self, tmp_path):
        prof = Profile(skills=Skills(
            languages={"Python": LanguageSkill(level=SkillLevel.EXPERT, lines=5000)},
        ))
        save_snapshot(prof, tmp_path, notes_count=1)
        save_snapshot(prof, tmp_path, notes_count=5)
        snapshots = load_snapshots(tmp_path)
        assert len(snapshots) == 1
        assert snapshots[0].notes_count == 5

    def test_empty_dir_returns_empty(self, tmp_path):
        assert load_snapshots(tmp_path) == []

    def test_corrupted_file_returns_empty(self, tmp_path):
        (tmp_path / "snapshots.json").write_text("not json", encoding="utf-8")
        assert load_snapshots(tmp_path) == []


class TestComputeDiff:
    def test_lines_delta(self):
        old = ProfileSnapshot(date="2026-01-01", total_lines=1000)
        new = ProfileSnapshot(date="2026-03-01", total_lines=5000)
        diff = compute_diff(old, new)
        assert diff["lines_delta"] == 4000
        assert diff["period"] == "2026-01-01 → 2026-03-01"

    def test_new_language(self):
        old = ProfileSnapshot(date="2026-01-01", skills=Skills(
            languages={"Python": LanguageSkill(level=SkillLevel.EXPERT)},
        ))
        new = ProfileSnapshot(date="2026-03-01", skills=Skills(
            languages={
                "Python": LanguageSkill(level=SkillLevel.EXPERT),
                "Go": LanguageSkill(level=SkillLevel.PROFICIENT),
            },
        ))
        diff = compute_diff(old, new)
        assert "Go" in diff["new_languages"]

    def test_level_up(self):
        old = ProfileSnapshot(date="2026-01-01", skills=Skills(
            languages={"Python": LanguageSkill(level=SkillLevel.PROFICIENT)},
        ))
        new = ProfileSnapshot(date="2026-03-01", skills=Skills(
            languages={"Python": LanguageSkill(level=SkillLevel.EXPERT)},
        ))
        diff = compute_diff(old, new)
        assert len(diff["level_ups"]) == 1
        assert diff["level_ups"][0]["skill"] == "Python"
        assert diff["level_ups"][0]["from"] == "proficient"
        assert diff["level_ups"][0]["to"] == "expert"

    def test_no_level_up_when_same(self):
        old = ProfileSnapshot(date="2026-01-01", skills=Skills(
            languages={"Python": LanguageSkill(level=SkillLevel.EXPERT)},
        ))
        new = ProfileSnapshot(date="2026-03-01", skills=Skills(
            languages={"Python": LanguageSkill(level=SkillLevel.EXPERT)},
        ))
        diff = compute_diff(old, new)
        assert diff["level_ups"] == []

    def test_domain_level_up(self):
        old = ProfileSnapshot(date="2026-01-01", skills=Skills(
            domains={"web": DomainSkill(level=SkillLevel.BEGINNER)},
        ))
        new = ProfileSnapshot(date="2026-03-01", skills=Skills(
            domains={"web": DomainSkill(level=SkillLevel.ADVANCED)},
        ))
        diff = compute_diff(old, new)
        assert len(diff["level_ups"]) == 1
        assert diff["level_ups"][0]["skill"] == "web"

    def test_new_domain(self):
        old = ProfileSnapshot(date="2026-01-01", skills=Skills())
        new = ProfileSnapshot(date="2026-03-01", skills=Skills(
            domains={"realtime": DomainSkill(level=SkillLevel.PROFICIENT)},
        ))
        diff = compute_diff(old, new)
        assert "realtime" in diff["new_domains"]

    def test_gaps_closed(self):
        old = ProfileSnapshot(date="2026-01-01", skills=Skills(
            domains={"web": DomainSkill(gaps=["testing", "security"])},
        ))
        new = ProfileSnapshot(date="2026-03-01", skills=Skills(
            domains={"web": DomainSkill(gaps=["security"])},
        ))
        diff = compute_diff(old, new)
        assert "testing" in diff["gaps_closed"]
        assert "security" not in diff["gaps_closed"]

    def test_empty_snapshots(self):
        old = ProfileSnapshot(date="2026-01-01")
        new = ProfileSnapshot(date="2026-03-01")
        diff = compute_diff(old, new)
        assert diff["lines_delta"] == 0
        assert diff["new_languages"] == []
        assert diff["level_ups"] == []
