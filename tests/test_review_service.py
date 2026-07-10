"""Shared review service 测试（Slice 0）。

契约测试重点：
- due summary / active-suspended 过滤只有一份实现；
- 服务端强制 limit <= 5；
- GUI 有意把 quality 0/1/2 折叠为 Again（reviewer 语义分化时这里必须失败）；
- 标准卡写回原文件、relationship 卡写回 _relationships.json；
- source path 缺失/歧义/越界返回 None；
- 跨进程锁下并发评分不丢更新；
- apply_outcome 幂等（绝对值快照，重放不重复推进/不重复 boost）。
"""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from neocortex.models import Flashcard
from neocortex.reviewer import get_review_session, is_active, sm2_update
from neocortex.services.review import (
    GUI_QUALITY_MAP,
    MAX_SESSION_CARDS,
    CardNotFoundError,
    ReviewServiceError,
    apply_outcome,
    clamp_session_limit,
    compute_outcome,
    find_stored_card,
    get_review_queue_summary,
    grade_card,
    load_stored_cards,
    resolve_source_path,
    select_session_cards,
    set_card_suspended,
)

TODAY = date.today().isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()
NEXT_WEEK = (date.today() + timedelta(days=7)).isoformat()


def _card(card_id: str, **kwargs) -> dict:
    base = {
        "id": card_id,
        "source_note": "note-a.md",
        "question": f"Q {card_id}?",
        "answer": f"A {card_id}.",
        "concept": "",
        "card_type": "standard",
        "interval": 1,
        "ease_factor": 2.5,
        "next_review": TODAY,
        "review_count": 0,
        "last_review": None,
    }
    base.update(kwargs)
    return base


def _write_cards(vault: Path, stem: str, cards: list[dict]) -> Path:
    fc = vault / ".flashcards"
    fc.mkdir(parents=True, exist_ok=True)
    path = fc / f"{stem}.json"
    path.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


# ── StoredCard 加载 ──


class TestLoadStoredCards:
    def test_records_true_storage_path(self, vault):
        _write_cards(vault, "note-a", [_card("a1"), _card("a2")])
        rel_path = _write_cards(
            vault, "_relationships",
            [_card("r1", source_note="", card_type="relationship", concept="X <> Y")],
        )
        stored = load_stored_cards(vault)
        assert len(stored) == 3
        rel = [s for s in stored if s.card.id == "r1"][0]
        assert rel.storage_path == rel_path
        assert rel.storage_key == "_relationships"

    def test_old_json_without_suspended_field_loads(self, vault):
        # 旧 JSON 没有 suspended 字段 → 默认 False（向后兼容）
        _write_cards(vault, "note-a", [_card("a1")])
        stored = load_stored_cards(vault)
        assert stored[0].card.suspended is False
        assert is_active(stored[0].card)

    def test_malformed_entry_skipped(self, vault):
        _write_cards(vault, "note-a", [_card("a1"), {"garbage": True}])
        assert [s.card.id for s in load_stored_cards(vault)] == ["a1"]


# ── 队列摘要（唯一实现）──


class TestQueueSummary:
    def test_due_total_and_next_due_date(self, vault):
        _write_cards(vault, "note-a", [
            _card("due1", next_review=TODAY),
            _card("due2", next_review=""),          # 无日期 = due
            _card("future", next_review=NEXT_WEEK),
        ])
        s = get_review_queue_summary(vault)
        assert s.due_total == 2
        assert {c.card.id for c in s.queue} == {"due1", "due2"}
        assert s.next_due_date == NEXT_WEEK

    def test_no_due_cards(self, vault):
        _write_cards(vault, "note-a", [_card("f1", next_review=TOMORROW)])
        s = get_review_queue_summary(vault)
        assert s.due_total == 0
        assert s.queue == []
        assert s.next_due_date == TOMORROW

    def test_suspended_excluded_everywhere(self, vault):
        _write_cards(vault, "note-a", [
            _card("live", next_review=TODAY),
            _card("dead", next_review=TODAY, suspended=True),
        ])
        s = get_review_queue_summary(vault)
        assert s.due_total == 1
        assert s.total_active == 1
        assert [c.card.id for c in s.queue] == ["live"]
        # config.get_due_flashcards 与 summary 是同一份谓词
        from neocortex.config import get_due_flashcards
        assert [c.id for c in get_due_flashcards(vault)] == ["live"]

    def test_summary_matches_get_due_flashcards(self, vault):
        _write_cards(vault, "note-a", [
            _card("a", next_review=TODAY),
            _card("b", next_review=NEXT_WEEK),
            _card("c", next_review="", suspended=True),
        ])
        from neocortex.config import get_due_flashcards
        s = get_review_queue_summary(vault)
        assert s.due_total == len(get_due_flashcards(vault))

    def test_empty_vault(self, vault):
        s = get_review_queue_summary(vault)
        assert s.due_total == 0
        assert s.next_due_date is None

    def test_explicit_today_controls_default_queue(self, vault):
        _write_cards(vault, "note-a", [
            _card("old", next_review="2026-01-01"),
            _card("later", next_review="2026-02-01"),
        ])
        s = get_review_queue_summary(vault, today="2026-01-15")
        assert [c.card.id for c in s.queue] == ["old"]
        assert s.due_total == 1
        assert s.next_due_date == "2026-02-01"


class TestSuspendedInReviewerModes:
    def test_all_modes_exclude_suspended(self):
        live = Flashcard.model_validate(_card("live", next_review=TODAY, ease_factor=1.5))
        dead = Flashcard.model_validate(
            _card("dead", next_review=TODAY, ease_factor=1.5, suspended=True))
        for mode in ("default", "diagnostic", "drill", "hard"):
            picked = get_review_session([live, dead], max_cards=10, mode=mode)
            assert all(c.id != "dead" for c in picked), mode


# ── limit 5 ──


class TestSessionLimit:
    def test_clamp(self):
        assert clamp_session_limit(None) == MAX_SESSION_CARDS
        assert clamp_session_limit(3) == 3
        assert clamp_session_limit(5) == 5
        assert clamp_session_limit(6) == 5
        assert clamp_session_limit(100) == 5
        assert clamp_session_limit(0) == 0
        assert clamp_session_limit(-1) == 0

    def test_select_never_exceeds_five(self, vault):
        _write_cards(vault, "note-a", [
            _card(f"c{i}", next_review=TODAY) for i in range(9)
        ])
        s = get_review_queue_summary(vault)
        assert s.due_total == 9
        assert len(select_session_cards(s, 20)) == 5
        assert len(select_session_cards(s, None)) == 5
        assert len(select_session_cards(s, 2)) == 2


# ── GUI quality 折叠契约 ──


class TestQualityFolding:
    """GUI 有意把 quality 0/1/2 折叠为 Again。

    该测试锁定 sm2_update 对 0/1/2 行为完全相同（interval=1、review_count=0、
    ease 不变）。如果这里失败，说明 reviewer.py 让 0/1/2 语义分化了——
    必须重新审视 services/review.py 的 GUI_QUALITY_MAP，不允许只改测试。
    """

    def test_quality_0_1_2_identical_reset(self):
        results = []
        for q in (0, 1, 2):
            card = Flashcard.model_validate(
                _card("x", interval=6, ease_factor=2.5, review_count=2))
            sm2_update(card, q)
            results.append((card.interval, card.review_count, card.ease_factor))
        assert results[0] == results[1] == results[2]
        interval, review_count, ease = results[0]
        assert interval == 1
        assert review_count == 0
        assert ease == 2.5  # ease 不变

    def test_gui_map_values(self):
        assert GUI_QUALITY_MAP == {"again": 0, "hard": 3, "good": 4, "easy": 5}


# ── 评分写回 ──


class TestGradeWriteback:
    def test_standard_card_written_back_to_own_file(self, vault):
        path = _write_cards(vault, "note-a", [_card("a1"), _card("a2")])
        outcome = grade_card(vault, "a1", 4)
        assert outcome.after["review_count"] == 1
        data = json.loads(path.read_text(encoding="utf-8"))
        by_id = {c["id"]: c for c in data}
        assert by_id["a1"]["review_count"] == 1
        assert by_id["a1"]["next_review"] == TOMORROW
        assert by_id["a2"]["review_count"] == 0  # 同文件其他卡不受影响

    def test_relationship_card_written_back_to_relationships_json(self, vault):
        rel_path = _write_cards(
            vault, "_relationships",
            [_card("r1", source_note="", card_type="relationship", concept="X <> Y")],
        )
        grade_card(vault, "r1", 5)
        data = json.loads(rel_path.read_text(encoding="utf-8"))
        assert data[0]["review_count"] == 1
        # 绝不能用 source_note("") 反推出错误文件
        assert not (vault / ".flashcards" / ".json").exists()

    def test_grade_boosts_standard_concept(self, vault):
        concepts = vault / "concepts"
        concepts.mkdir()
        (concepts / "know-x.md").write_text(
            "---\nconfidence: 0.5\nlast_updated: " + TODAY + "\n---\nbody",
            encoding="utf-8",
        )
        _write_cards(vault, "note-a", [_card("a1", concept="Know X")])
        grade_card(vault, "a1", 4)
        content = (concepts / "know-x.md").read_text(encoding="utf-8")
        conf = float(content.split("confidence: ")[1].split("\n")[0])
        assert conf > 0.5
        assert f"last_updated: {TODAY}" in content

    def test_failed_grade_does_not_boost(self, vault):
        concepts = vault / "concepts"
        concepts.mkdir()
        (concepts / "know-x.md").write_text(
            "---\nconfidence: 0.5\nlast_updated: " + TODAY + "\n---\n",
            encoding="utf-8",
        )
        _write_cards(vault, "note-a", [_card("a1", concept="Know X")])
        grade_card(vault, "a1", 0)  # Again
        content = (concepts / "know-x.md").read_text(encoding="utf-8")
        assert "confidence: 0.5" in content

    def test_relationship_card_never_boosts(self, vault):
        # relationship card 的 concept 是组合标签，没有明确的两个 concept ID
        # 之前不伪造 boost —— 即使碰巧存在同名 concept 文件也不碰。
        concepts = vault / "concepts"
        concepts.mkdir()
        (concepts / "x-<>-y.md").write_text(
            "---\nconfidence: 0.5\nlast_updated: 2026-01-01\n---\n",
            encoding="utf-8",
        )
        _write_cards(
            vault, "_relationships",
            [_card("r1", source_note="", card_type="relationship", concept="X <> Y")],
        )
        outcome = grade_card(vault, "r1", 5)
        assert outcome.concept_boost is None
        assert "confidence: 0.5" in (concepts / "x-<>-y.md").read_text(encoding="utf-8")

    def test_unknown_card_raises(self, vault):
        _write_cards(vault, "note-a", [_card("a1")])
        with pytest.raises(CardNotFoundError):
            grade_card(vault, "nope", 4)


# ── suspend / restore ──


class TestSuspendRestore:
    def test_suspend_then_restore_roundtrip(self, vault):
        path = _write_cards(vault, "note-a", [_card("a1")])
        out = set_card_suspended(vault, "a1", True)
        assert out.after["suspended"] is True
        assert json.loads(path.read_text())[0]["suspended"] is True
        assert get_review_queue_summary(vault).due_total == 0

        out2 = set_card_suspended(vault, "a1", False)
        assert out2.after["suspended"] is False
        assert get_review_queue_summary(vault).due_total == 1

    def test_suspend_preserves_schedule(self, vault):
        _write_cards(vault, "note-a", [_card("a1", interval=6, review_count=2)])
        out = set_card_suspended(vault, "a1", True)
        assert out.after["interval"] == 6
        assert out.after["review_count"] == 2


# ── apply_outcome 幂等 ──


class TestApplyIdempotent:
    def test_reapply_same_outcome_no_double_advance(self, vault):
        concepts = vault / "concepts"
        concepts.mkdir()
        (concepts / "know-x.md").write_text(
            "---\nconfidence: 0.5\nlast_updated: " + TODAY + "\n---\n",
            encoding="utf-8",
        )
        path = _write_cards(vault, "note-a", [_card("a1", concept="Know X")])
        stored = find_stored_card(vault, "a1")
        outcome = compute_outcome(vault, stored, "grade", quality=4)

        apply_outcome(vault, outcome)
        first_card = json.loads(path.read_text())[0]
        first_concept = (concepts / "know-x.md").read_text(encoding="utf-8")

        # 重放同一个 outcome：绝对值赋值，不重复推进、不重复 boost
        apply_outcome(vault, outcome)
        assert json.loads(path.read_text())[0] == first_card
        assert (concepts / "know-x.md").read_text(encoding="utf-8") == first_concept
        assert first_card["review_count"] == 1

    def test_pending_outcome_survives_layout_move(self, tmp_path):
        old_vault = tmp_path / "old-layout" / "vault"
        old_vault.mkdir(parents=True)
        _write_cards(old_vault, "note-a", [_card("a1")])
        outcome = compute_outcome(
            old_vault, find_stored_card(old_vault, "a1"), "grade", quality=4)

        assert outcome.storage_path == "note-a.json"
        new_vault = tmp_path / "moved-layout" / "vault"
        new_vault.parent.mkdir()
        old_vault.rename(new_vault)

        apply_outcome(new_vault, outcome)
        card = json.loads(
            (new_vault / ".flashcards" / "note-a.json").read_text())[0]
        assert card["review_count"] == 1

    def test_legacy_absolute_pending_path_uses_safe_basename_after_move(self, tmp_path):
        old_vault = tmp_path / "old-vault"
        old_vault.mkdir()
        old_path = _write_cards(old_vault, "note-a", [_card("a1")])
        outcome = compute_outcome(
            old_vault, find_stored_card(old_vault, "a1"), "grade", quality=4)
        legacy = replace(outcome, storage_path=str(old_path))

        new_vault = tmp_path / "new-vault"
        old_vault.rename(new_vault)
        apply_outcome(new_vault, legacy)
        assert json.loads(
            (new_vault / ".flashcards" / "note-a.json").read_text())[0][
                "review_count"] == 1

    def test_persisted_storage_reference_cannot_escape_flashcards(self, vault):
        _write_cards(vault, "note-a", [_card("a1")])
        outcome = compute_outcome(
            vault, find_stored_card(vault, "a1"), "grade", quality=4)
        outside = vault / "outside.json"
        outside.write_text(json.dumps([_card("a1")]), encoding="utf-8")
        before = outside.read_text(encoding="utf-8")

        with pytest.raises(ReviewServiceError):
            apply_outcome(vault, replace(outcome, storage_path="../outside.json"))

        assert outside.read_text(encoding="utf-8") == before


# ── 多模型 review 修复的回归锁定 ──


class TestConceptPathEscape:
    """concept 名来自卡片数据，不可信：禁止任何路径逃逸（Codex P1）。"""

    def test_compute_boost_rejects_escaping_concept(self, vault):
        from neocortex.services.review import compute_concept_boost

        (vault / "evil.md").write_text(
            "---\nconfidence: 0.5\nlast_updated: 2026-01-01\n---\n", encoding="utf-8")
        for name in ("../evil", "../../evil", "/etc/evil", "a/b", ".hidden", "~x"):
            assert compute_concept_boost(vault, name) is None, name

    def test_apply_boost_rejects_escaping_snapshot(self, vault, tmp_path):
        # 快照可能从 SQLite 恢复而来，apply 阶段必须重新校验
        from neocortex.services.review import _apply_concept_boost

        outside = vault.parent / "outside.md"
        outside.write_text(
            "---\nconfidence: 0.5\nlast_updated: 2026-01-01\n---\n", encoding="utf-8")
        before = outside.read_text(encoding="utf-8")
        for bad in ("../outside.md", "concepts/../../outside.md", "/etc/passwd"):
            _apply_concept_boost(vault, {
                "concept_path": bad,
                "before_confidence": 0.5,
                "confidence": 0.9,
                "last_updated": TODAY,
            })
        assert outside.read_text(encoding="utf-8") == before


class TestApplyPreservesUnknownEntries:
    """容错读取绝不能变成破坏性写回（Codex P1 / Kimi critical）。"""

    def test_grade_preserves_malformed_sibling_entries(self, vault):
        garbage = {"totally": "unrelated", "shape": [1, 2, 3]}
        path = _write_cards(vault, "note-a", [_card("a1"), garbage])
        grade_card(vault, "a1", 4)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert garbage in data  # 坏条目原样保留
        by_id = {c.get("id"): c for c in data if isinstance(c, dict) and "id" in c}
        assert by_id["a1"]["review_count"] == 1

    def test_grade_preserves_unknown_extra_fields_on_target(self, vault):
        card = _card("a1")
        card["future_field"] = "keep me"
        path = _write_cards(vault, "note-a", [card])
        grade_card(vault, "a1", 4)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data[0]["future_field"] == "keep me"
        assert data[0]["review_count"] == 1


class TestBoostConflictDetection:
    """boost 三态应用：未应用→写；已应用→跳过；被他人更新→保留新值（Codex/Pi P2）。"""

    def _concept(self, vault, confidence: str) -> Path:
        concepts = vault / "concepts"
        concepts.mkdir(exist_ok=True)
        p = concepts / "know-x.md"
        p.write_text(
            f"---\nconfidence: {confidence}\nlast_updated: 2026-01-01\n---\n",
            encoding="utf-8")
        return p

    def test_conflicting_newer_confidence_not_clobbered(self, vault):
        from neocortex.services.review import _apply_concept_boost

        p = self._concept(vault, "0.9")  # 期间被 compiler/CLI 合法更新
        _apply_concept_boost(vault, {
            "concept_path": "concepts/know-x.md",
            "before_confidence": 0.5,
            "confidence": 0.55,
            "last_updated": TODAY,
        })
        assert "confidence: 0.9" in p.read_text(encoding="utf-8")

    def test_matching_before_applies(self, vault):
        from neocortex.services.review import _apply_concept_boost

        p = self._concept(vault, "0.5")
        _apply_concept_boost(vault, {
            "concept_path": "concepts/know-x.md",
            "before_confidence": 0.5,
            "confidence": 0.55,
            "last_updated": TODAY,
        })
        assert "confidence: 0.5500" in p.read_text(encoding="utf-8")


class TestSaveFlashcardsLocking:
    """compiler/cmd_read 的整文件写与复习共用同一把跨进程锁（Pi HIGH）。"""

    def test_save_flashcards_waits_for_review_lock(self, vault):
        import time
        from neocortex.config import save_flashcards
        from neocortex.services.review import review_write_lock

        card = Flashcard.model_validate(_card("a1"))
        done = threading.Event()

        def writer():
            save_flashcards(vault, "note-a", [card])
            done.set()

        with review_write_lock(vault):
            t = threading.Thread(target=writer)
            t.start()
            time.sleep(0.3)
            assert not done.is_set()  # 锁被持有期间写入必须阻塞
        t.join(timeout=5)
        assert done.is_set()


# ── source path 解析 ──


class TestResolveSourcePath:
    def test_empty_returns_none(self, vault):
        assert resolve_source_path(vault, "") is None

    def test_unique_basename_match(self, vault):
        (vault / "clips").mkdir()
        (vault / "clips" / "note-a.md").write_text("x", encoding="utf-8")
        assert resolve_source_path(vault, "note-a.md") == "clips/note-a.md"

    def test_missing_returns_none(self, vault):
        assert resolve_source_path(vault, "ghost.md") is None

    def test_ambiguous_returns_none(self, vault):
        (vault / "clips").mkdir()
        (vault / "insights").mkdir()
        (vault / "clips" / "dup.md").write_text("x", encoding="utf-8")
        (vault / "insights" / "dup.md").write_text("y", encoding="utf-8")
        assert resolve_source_path(vault, "dup.md") is None

    def test_hidden_dirs_not_matched(self, vault):
        (vault / ".flashcards").mkdir()
        (vault / ".flashcards" / "hidden.md").write_text("x", encoding="utf-8")
        assert resolve_source_path(vault, "hidden.md") is None

    def test_vault_relative_path_accepted(self, vault):
        (vault / "clips").mkdir()
        (vault / "clips" / "note-b.md").write_text("x", encoding="utf-8")
        assert resolve_source_path(vault, "clips/note-b.md") == "clips/note-b.md"

    def test_vault_relative_missing_returns_none(self, vault):
        assert resolve_source_path(vault, "clips/ghost.md") is None

    def test_escape_rejected(self, vault, tmp_path):
        outside = tmp_path / "outside.md"
        outside.write_text("secret", encoding="utf-8")
        assert resolve_source_path(vault, "../outside.md") is None
        assert resolve_source_path(vault, str(outside)) is None
        assert resolve_source_path(vault, "~/outside.md") is None
        assert resolve_source_path(vault, "clips/../../outside.md") is None


# ── 并发写入 ──


class TestConcurrentWrites:
    def test_parallel_grades_same_file_no_lost_update(self, vault):
        """两个写者同时评分同一文件里的不同卡：flock 串行化，双方更新都落盘。

        flock 锁在 open file description 上，同进程两次独立 open 也互斥，
        所以线程 + 独立文件句柄即可模拟跨进程行为。
        """
        path = _write_cards(vault, "note-a", [_card("a1"), _card("a2")])
        errors: list[Exception] = []

        def work(card_id: str) -> None:
            try:
                for _ in range(5):
                    grade_card(vault, card_id, 4)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        t1 = threading.Thread(target=work, args=("a1",))
        t2 = threading.Thread(target=work, args=("a2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors
        data = {c["id"]: c for c in json.loads(path.read_text())}
        assert data["a1"]["review_count"] == 5
        assert data["a2"]["review_count"] == 5


# ── daily 服务复用 ──


class TestDailyUsesSharedSummary:
    @pytest.mark.asyncio
    async def test_daily_due_count_equals_summary(self, vault, monkeypatch):
        from neocortex.models import AppConfig, Profile
        from neocortex.services.daily import build_briefing

        _write_cards(vault, "note-a", [
            _card("d1", next_review=TODAY),
            _card("d2", next_review=TODAY),
            _card("s1", next_review=TODAY, suspended=True),
            _card("f1", next_review=NEXT_WEEK),
        ])
        briefing = await build_briefing(
            notes_dir=vault,
            cfg=AppConfig(),
            profile=Profile(),
            lang="en",
        )
        summary = get_review_queue_summary(vault)
        assert briefing.due_flashcard_count == summary.due_total == 2
