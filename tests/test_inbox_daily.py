from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.models import Clip, Language


def _make_clip(
    *,
    id: str = "abc123",
    title: str = "Test clip",
    status: str = "inbox",
    clip_type: str = "bookmark",
    created_at: str | None = None,
    related_concepts: list[str] | None = None,
    next_surface: str = "",
    surface_count: int = 0,
    source: str = "https://example.com",
    summary: str = "A test summary",
    content: str = "Test content",
    topic: str = "general",
) -> Clip:
    return Clip(
        id=id,
        source=source,
        content=content,
        title=title,
        clip_type=clip_type,
        status=status,
        summary=summary,
        created_at=created_at or date.today().isoformat(),
        related_concepts=related_concepts or [],
        next_surface=next_surface,
        surface_count=surface_count,
        topic=topic,
    )


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path / "notes")
    (tmp_path / "notes").mkdir(exist_ok=True)
    (tmp_path / "notes" / "clips").mkdir(exist_ok=True)
    config_data = {
        "provider": "openai",
        "api_key": "test-key",
        "output_settings": {"language": "en", "notes_dir": str(tmp_path / "notes")},
    }
    (tmp_path / "config.json").write_text(json.dumps(config_data), encoding="utf-8")


class TestInboxList:
    def test_inbox_list_shows_clips(self):
        clips = [
            _make_clip(id="a1", title="First", clip_type="tweet"),
            _make_clip(id="a2", title="Second", clip_type="bookmark"),
        ]
        from neocortex.cmd_clip import _inbox_list

        _inbox_list(clips, Language.EN)

    def test_inbox_list_empty(self):
        from neocortex.cmd_clip import _inbox_list

        _inbox_list([], Language.EN)

    def test_inbox_list_truncates_long_titles(self):
        clip = _make_clip(title="A" * 100)
        from neocortex.cmd_clip import _inbox_list

        _inbox_list([clip], Language.EN)


class TestInboxProcess:
    def test_process_keep(self, tmp_path):
        clip = _make_clip(id="k1", title="Keep me")
        saved_clips = []

        def mock_save(notes_dir, c):
            saved_clips.append(c)
            return notes_dir / "clips" / f"{c.id}.md"

        with patch("neocortex.config.save_clip", mock_save), \
             patch("rich.prompt.Prompt.ask", return_value="k"):
            from neocortex.cmd_clip import _inbox_process

            _inbox_process([clip], tmp_path / "notes", Language.EN)

        assert len(saved_clips) == 1
        assert saved_clips[0].status == "reference"
        assert saved_clips[0].processed_at is not None

    def test_process_delete(self, tmp_path):
        clip = _make_clip(id="d1", title="Delete me")
        saved_clips = []

        def mock_save(notes_dir, c):
            saved_clips.append(c)
            return notes_dir / "clips" / f"{c.id}.md"

        with patch("neocortex.config.save_clip", mock_save), \
             patch("rich.prompt.Prompt.ask", return_value="d"):
            from neocortex.cmd_clip import _inbox_process

            _inbox_process([clip], tmp_path / "notes", Language.EN)

        assert saved_clips[0].status == "archived"

    def test_process_promote(self, tmp_path):
        clip = _make_clip(id="r1", title="Read me", source="https://example.com/article")
        saved_clips = []

        def mock_save(notes_dir, c):
            saved_clips.append(c)
            return notes_dir / "clips" / f"{c.id}.md"

        with patch("neocortex.config.save_clip", mock_save), \
             patch("rich.prompt.Prompt.ask", return_value="r"):
            from neocortex.cmd_clip import _inbox_process

            _inbox_process([clip], tmp_path / "notes", Language.EN)

        assert saved_clips[0].status == "promoted"
        assert saved_clips[0].promoted_to == "https://example.com/article"

    def test_process_skip_does_not_save(self, tmp_path):
        clip = _make_clip(id="s1", title="Skip me")
        saved_clips = []

        def mock_save(notes_dir, c):
            saved_clips.append(c)
            return notes_dir / "clips" / f"{c.id}.md"

        with patch("neocortex.config.save_clip", mock_save), \
             patch("rich.prompt.Prompt.ask", return_value="s"):
            from neocortex.cmd_clip import _inbox_process

            _inbox_process([clip], tmp_path / "notes", Language.EN)

        assert len(saved_clips) == 0

    def test_process_empty_inbox(self, tmp_path):
        from neocortex.cmd_clip import _inbox_process

        _inbox_process([], tmp_path / "notes", Language.EN)


class TestInboxSynthesize:
    def test_synthesize_detects_clusters_no_provider(self, tmp_path):
        clips = [
            _make_clip(id="c1", related_concepts=["asyncio"], status="inbox"),
            _make_clip(id="c2", related_concepts=["asyncio"], status="inbox"),
            _make_clip(id="c3", related_concepts=["asyncio"], status="reference"),
        ]
        from neocortex.models import AppConfig
        from neocortex.cmd_clip import _inbox_synthesize

        with patch("neocortex.config.load_config", return_value=AppConfig()):
            _inbox_synthesize(clips, tmp_path / "notes", Language.EN)

    def test_synthesize_no_clusters(self, tmp_path):
        clips = [
            _make_clip(id="c1", related_concepts=["asyncio"], status="inbox"),
            _make_clip(id="c2", related_concepts=["react"], status="inbox"),
        ]
        from neocortex.cmd_clip import _inbox_synthesize

        _inbox_synthesize(clips, tmp_path / "notes", Language.EN)

    def test_synthesize_generates_note(self, tmp_path):
        clips = [
            _make_clip(id="c1", title="Clip 1", related_concepts=["asyncio"], status="inbox", summary="About async"),
            _make_clip(id="c2", title="Clip 2", related_concepts=["asyncio"], status="inbox", summary="More async"),
            _make_clip(id="c3", title="Clip 3", related_concepts=["asyncio"], status="reference", summary="Async deep"),
        ]

        notes_dir = tmp_path / "notes"
        notes_dir.mkdir(exist_ok=True)
        saved_clips = []

        def mock_save(nd, c):
            saved_clips.append(c)
            return nd / "clips" / f"{c.id}.md"

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value="## Threads\nAsync is trending\n\n## Consensus\nAll agree async is good")

        from neocortex.models import AppConfig, ProviderType

        fake_cfg = AppConfig(provider=ProviderType.OPENAI, api_key="test-key")

        with patch("neocortex.config.save_clip", mock_save), \
             patch("neocortex.config.load_config", return_value=fake_cfg), \
             patch("neocortex.llm.create_provider", return_value=mock_provider):
            from neocortex.cmd_clip import _inbox_synthesize

            _inbox_synthesize(clips, notes_dir, Language.EN)

        note_file = notes_dir / "synthesis-asyncio.md"
        assert note_file.exists()
        content = note_file.read_text(encoding="utf-8")
        assert "Synthesis: asyncio" in content
        assert len(saved_clips) == 3
        for c in saved_clips:
            assert c.status == "synthesized"


class TestDailySurfacing:
    def test_surface_filters_due_clips(self):
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        clips = [
            _make_clip(id="due1", next_surface=yesterday, status="inbox"),
            _make_clip(id="due2", next_surface=today, status="reference"),
            _make_clip(id="not_due", next_surface=tomorrow, status="inbox"),
            _make_clip(id="no_surface", next_surface="", status="inbox"),
        ]

        surfacing = [
            c for c in clips
            if c.status in ("inbox", "reference")
            and c.next_surface
            and c.next_surface <= today
        ]

        assert len(surfacing) == 2
        assert {c.id for c in surfacing} == {"due1", "due2"}

    def test_surface_schedule_update(self, tmp_path):
        from neocortex.cmd_daily import SURFACE_INTERVALS, _update_surface_schedule

        clip = _make_clip(id="sched1", surface_count=0, next_surface=date.today().isoformat())
        saved_clips = []

        def mock_save(nd, c):
            saved_clips.append(c)
            return nd / "clips" / f"{c.id}.md"

        context_updates = [{"context_update": "", "absorbed": False}]
        _update_surface_schedule([clip], context_updates, tmp_path, mock_save)

        assert len(saved_clips) == 1
        expected_next = (date.today() + timedelta(days=SURFACE_INTERVALS[1])).isoformat()
        assert saved_clips[0].next_surface == expected_next
        assert saved_clips[0].surface_count == 1

    def test_surface_schedule_absorbed(self, tmp_path):
        from neocortex.cmd_daily import _update_surface_schedule

        clip = _make_clip(id="abs1", surface_count=1, next_surface=date.today().isoformat())
        saved_clips = []

        def mock_save(nd, c):
            saved_clips.append(c)
            return nd / "clips" / f"{c.id}.md"

        context_updates = [{"context_update": "Covered in notes", "absorbed": True}]
        _update_surface_schedule([clip], context_updates, tmp_path, mock_save)

        expected_next = (date.today() + timedelta(days=180)).isoformat()
        assert saved_clips[0].next_surface == expected_next

    def test_surface_schedule_max_interval(self, tmp_path):
        from neocortex.cmd_daily import SURFACE_INTERVALS, _update_surface_schedule

        clip = _make_clip(id="max1", surface_count=len(SURFACE_INTERVALS), next_surface=date.today().isoformat())
        saved_clips = []

        def mock_save(nd, c):
            saved_clips.append(c)
            return nd / "clips" / f"{c.id}.md"

        context_updates = [{"context_update": "", "absorbed": False}]
        _update_surface_schedule([clip], context_updates, tmp_path, mock_save)

        expected_next = (date.today() + timedelta(days=90)).isoformat()
        assert saved_clips[0].next_surface == expected_next


class TestDailyCluster:
    def test_cluster_detection(self):
        from neocortex.cmd_daily import _detect_clusters

        clips = [
            _make_clip(id="c1", related_concepts=["asyncio"], status="inbox"),
            _make_clip(id="c2", related_concepts=["asyncio"], status="inbox"),
            _make_clip(id="c3", related_concepts=["asyncio"], status="reference"),
            _make_clip(id="c4", related_concepts=["react"], status="inbox"),
        ]
        _detect_clusters(clips, Language.EN)

    def test_no_clusters(self):
        from neocortex.cmd_daily import _detect_clusters

        clips = [
            _make_clip(id="c1", related_concepts=["asyncio"], status="inbox"),
            _make_clip(id="c2", related_concepts=["react"], status="inbox"),
        ]
        _detect_clusters(clips, Language.EN)


class TestDailyAbsorbed:
    def test_absorbed_clip_gets_long_interval(self, tmp_path):
        from neocortex.cmd_daily import _update_surface_schedule

        clip = _make_clip(id="abs2", surface_count=0, next_surface=date.today().isoformat())
        saved_clips = []

        def mock_save(nd, c):
            saved_clips.append(c)
            return nd / "clips" / f"{c.id}.md"

        context_updates = [{"context_update": "Already in notes", "absorbed": True}]
        _update_surface_schedule([clip], context_updates, tmp_path, mock_save)

        expected_next = (date.today() + timedelta(days=180)).isoformat()
        assert saved_clips[0].next_surface == expected_next
        assert saved_clips[0].surface_count == 1


class TestEmptyCases:
    def test_empty_inbox_no_crash(self):
        from neocortex.cmd_clip import _inbox_list

        _inbox_list([], Language.EN)

    def test_empty_clips_daily(self):
        from neocortex.cmd_daily import _detect_clusters, _display_surfacing

        _detect_clusters([], Language.EN)
        _display_surfacing([], [], Language.EN)

    def test_process_empty(self, tmp_path):
        from neocortex.cmd_clip import _inbox_process

        _inbox_process([], tmp_path / "notes", Language.EN)

    def test_synthesize_empty(self, tmp_path):
        from neocortex.cmd_clip import _inbox_synthesize

        _inbox_synthesize([], tmp_path / "notes", Language.EN)


# ── Health pulse ──


class TestHealthPulse:
    def test_no_reports_shows_suggestion(self, tmp_path):
        from neocortex.cmd_daily import _show_health_pulse

        notes_dir = tmp_path / "notes"
        notes_dir.mkdir(exist_ok=True)
        _show_health_pulse(notes_dir, Language.EN)

    def test_lint_report_shows_score(self, tmp_path):
        from neocortex.cmd_daily import _show_health_pulse

        notes_dir = tmp_path / "notes"
        reports_dir = notes_dir / "_reports"
        reports_dir.mkdir(parents=True)

        (reports_dir / "lint-2026-04-14.md").write_text(
            "---\ntype: lint-report\ndate: 2026-04-14\nscore: 75\n---\n",
            encoding="utf-8",
        )

        _show_health_pulse(notes_dir, Language.EN)

    def test_lint_trend_with_two_reports(self, tmp_path):
        from neocortex.cmd_daily import _show_health_pulse

        notes_dir = tmp_path / "notes"
        reports_dir = notes_dir / "_reports"
        reports_dir.mkdir(parents=True)

        (reports_dir / "lint-2026-04-13.md").write_text(
            "---\nscore: 70\n---\n", encoding="utf-8",
        )
        (reports_dir / "lint-2026-04-14.md").write_text(
            "---\nscore: 80\n---\n", encoding="utf-8",
        )

        _show_health_pulse(notes_dir, Language.EN)

    def test_verify_report_shows_fidelity(self, tmp_path):
        from neocortex.cmd_daily import _show_health_pulse

        notes_dir = tmp_path / "notes"
        reports_dir = notes_dir / "_reports"
        reports_dir.mkdir(parents=True)

        (reports_dir / "verify-2026-04-14.md").write_text(
            "---\nfidelity_score: 85\n---\n", encoding="utf-8",
        )

        _show_health_pulse(notes_dir, Language.EN)

    def test_both_reports(self, tmp_path):
        from neocortex.cmd_daily import _show_health_pulse

        notes_dir = tmp_path / "notes"
        reports_dir = notes_dir / "_reports"
        reports_dir.mkdir(parents=True)

        (reports_dir / "lint-2026-04-14.md").write_text(
            "---\nscore: 90\n---\n", encoding="utf-8",
        )
        (reports_dir / "verify-2026-04-14.md").write_text(
            "---\nfidelity_score: 88\n---\n", encoding="utf-8",
        )

        _show_health_pulse(notes_dir, Language.EN)


class TestSparkline:
    def test_sparkline_basic(self):
        from neocortex.cmd_daily import _sparkline

        result = _sparkline([50, 60, 70, 80, 90, 100])
        assert len(result) == 6
        assert result[0] != result[-1]

    def test_sparkline_flat(self):
        from neocortex.cmd_daily import _sparkline

        result = _sparkline([80, 80, 80])
        assert len(result) == 3

    def test_sparkline_empty(self):
        from neocortex.cmd_daily import _sparkline

        assert _sparkline([]) == ""


class TestReadReportScores:
    def test_reads_lint_scores(self, tmp_path):
        from neocortex.cmd_daily import _read_report_scores

        reports_dir = tmp_path / "_reports"
        reports_dir.mkdir()

        (reports_dir / "lint-2026-04-10.md").write_text(
            "---\nscore: 70\n---\n", encoding="utf-8",
        )
        (reports_dir / "lint-2026-04-12.md").write_text(
            "---\nscore: 85\n---\n", encoding="utf-8",
        )

        scores = _read_report_scores(reports_dir, "lint", "score")
        assert len(scores) == 2
        assert scores[0] == ("2026-04-12", 85)
        assert scores[1] == ("2026-04-10", 70)

    def test_no_reports_dir(self, tmp_path):
        from neocortex.cmd_daily import _read_report_scores

        scores = _read_report_scores(tmp_path / "nonexistent", "lint", "score")
        assert scores == []

    def test_reads_verify_scores(self, tmp_path):
        from neocortex.cmd_daily import _read_report_scores

        reports_dir = tmp_path / "_reports"
        reports_dir.mkdir()

        (reports_dir / "verify-2026-04-14.md").write_text(
            "---\nfidelity_score: 92\n---\n", encoding="utf-8",
        )

        scores = _read_report_scores(reports_dir, "verify", "fidelity_score")
        assert len(scores) == 1
        assert scores[0] == ("2026-04-14", 92)
