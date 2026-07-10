"""Review HTTP API + 事件存储测试（Slice 1）。

覆盖门禁：
- 安全边界（无 token / 错 Host / 非 JSON）；
- daily / impression 不创建 session，只有 POST /api/review/session 创建；
- daily due_flashcard_count == session due_total（同一快照）；
- session 永不超过 5；
- event_id 重放零副作用；
- 崩溃窗口恢复（JSON 已写 SQLite 未标记 / SQLite pending JSON 未写 / 状态被
  其他写者推进 → stale）；
- concept boost 不因恢复流程重复累加；
- 空 session / 未知卡 / 未知 session / 非法 action 的明确响应。
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from neocortex.services.review import grade_card
from neocortex.services.review_events import (
    ReviewEventStore,
    ReviewFlowError,
    create_review_session,
    handle_review_action,
)

TOKEN = "test-token-1234567890"
PORT = 8765
EXPECTED_HOST = f"127.0.0.1:{PORT}"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

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


def _session_body(
    *, limit: int = 5, entry_point: str = "menu", request_id: str | None = None,
) -> dict:
    return {
        "request_id": request_id or str(uuid.uuid4()),
        "limit": limit,
        "entry_point": entry_point,
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: vault)
    monkeypatch.setattr("neocortex.config.get_data_dir", lambda: data)

    from neocortex.server.app import create_app

    app = create_app(token=TOKEN, port=PORT)
    client = TestClient(app, base_url=f"http://{EXPECTED_HOST}")
    store = ReviewEventStore(data / "neocortex.sqlite")
    return SimpleNamespace(vault=vault, data=data, client=client, store=store)


# ── 安全边界 ──


class TestSecurity:
    def test_session_requires_token(self, env):
        r = env.client.post("/api/review/session", json=_session_body())
        assert r.status_code == 401

    def test_action_requires_token(self, env):
        r = env.client.post("/api/review/action", json={"event_id": "e" * 12, "action": "impression"})
        assert r.status_code == 401

    def test_wrong_host_rejected(self, env):
        r = env.client.post(
            "/api/review/session",
            json=_session_body(),
            headers={**AUTH, "Host": "evil.com"},
        )
        assert r.status_code == 400

    def test_bad_origin_rejected(self, env):
        r = env.client.post(
            "/api/review/session",
            json=_session_body(),
            headers={**AUTH, "Origin": "https://evil.com"},
        )
        assert r.status_code == 403

    def test_non_json_mutating_request_rejected(self, env):
        r = env.client.post(
            "/api/review/session",
            content="limit=5",
            headers={**AUTH, "Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 415


# ── session 创建 ──


class TestSessionCreation:
    def test_daily_does_not_create_session(self, env):
        _write_cards(env.vault, "note-a", [_card("a1")])
        r = env.client.get("/api/daily", headers=AUTH)
        assert r.status_code == 200
        assert env.store.session_count() == 0

    def test_impression_does_not_create_session(self, env):
        _write_cards(env.vault, "note-a", [_card("a1")])
        r = env.client.post(
            "/api/review/action",
            json={"event_id": "imp-0001", "action": "impression"},
            headers=AUTH,
        )
        assert r.status_code == 200
        assert r.json()["due_total"] == 1
        assert env.store.session_count() == 0

    def test_post_session_creates_exactly_one(self, env):
        _write_cards(env.vault, "note-a", [_card("a1"), _card("a2")])
        r = env.client.post(
            "/api/review/session",
            json=_session_body(),
            headers=AUTH,
        )
        assert r.status_code == 200
        body = r.json()
        assert env.store.session_count() == 1
        assert body["due_total"] == 2
        assert body["offered_count"] == 2
        assert len(body["cards"]) == 2
        card = body["cards"][0]
        for key in ("card_id", "question", "answer", "concept", "source_path", "source_available"):
            assert key in card

    def test_session_request_id_replay_returns_same_session(self, env):
        _write_cards(env.vault, "note-a", [_card("a1"), _card("a2")])
        request = _session_body(request_id="session-request-0001")
        first = env.client.post("/api/review/session", json=request, headers=AUTH)
        replay = env.client.post("/api/review/session", json=request, headers=AUTH)
        assert first.status_code == replay.status_code == 200
        assert replay.json() == first.json()
        assert env.store.session_count() == 1

    def test_legacy_session_without_request_id_remains_compatible(self, env):
        _write_cards(env.vault, "note-a", [_card("a1")])
        r = env.client.post(
            "/api/review/session",
            json={"limit": 5, "entry_point": "menu"},
            headers=AUTH,
        )
        assert r.status_code == 200
        assert r.json()["offered_count"] == 1
        assert env.store.session_count() == 1

    def test_session_limit_clamped_to_five(self, env):
        _write_cards(env.vault, "note-a", [_card(f"c{i}") for i in range(9)])
        r = env.client.post(
            "/api/review/session",
            json=_session_body(limit=50),
            headers=AUTH,
        )
        body = r.json()
        assert body["due_total"] == 9
        assert body["offered_count"] == 5
        assert len(body["cards"]) == 5

    def test_empty_due_returns_200_empty_cards(self, env):
        _write_cards(env.vault, "note-a", [_card("f1", next_review=NEXT_WEEK)])
        r = env.client.post(
            "/api/review/session",
            json=_session_body(),
            headers=AUTH,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["cards"] == []
        assert body["due_total"] == 0
        assert body["next_due_date"] == NEXT_WEEK
        # 空 session 也是真实记录（用户点了开始但无卡），立即完成
        session = env.store.get_session(body["session_id"])
        assert session["completed_at"] is not None

    def test_daily_count_equals_session_due_total(self, env):
        _write_cards(env.vault, "note-a", [
            _card("a1"), _card("a2"),
            _card("s1", suspended=True),
            _card("f1", next_review=NEXT_WEEK),
        ])
        daily = env.client.get("/api/daily", headers=AUTH).json()
        session = env.client.post(
            "/api/review/session",
            json=_session_body(),
            headers=AUTH,
        ).json()
        assert daily["due_flashcard_count"] == session["due_total"] == 2

    def test_source_resolution_in_cards(self, env):
        (env.vault / "clips").mkdir()
        (env.vault / "clips" / "note-a.md").write_text("x", encoding="utf-8")
        _write_cards(env.vault, "note-a", [
            _card("ok", source_note="note-a.md"),
            _card("missing", source_note="ghost.md"),
        ])
        body = env.client.post(
            "/api/review/session",
            json=_session_body(),
            headers=AUTH,
        ).json()
        by_id = {c["card_id"]: c for c in body["cards"]}
        assert by_id["ok"]["source_available"] is True
        assert by_id["ok"]["source_path"] == "clips/note-a.md"
        assert by_id["missing"]["source_available"] is False
        assert by_id["missing"]["source_path"] is None


# ── action 语义 ──


def _start_session(env, limit=5) -> dict:
    return env.client.post(
        "/api/review/session",
        json=_session_body(limit=limit, entry_point="test"),
        headers=AUTH,
    ).json()


def _action(env, **kwargs):
    return env.client.post("/api/review/action", json=kwargs, headers=AUTH)


class TestActions:
    def test_grade_updates_card(self, env):
        path = _write_cards(env.vault, "note-a", [_card("a1")])
        s = _start_session(env)
        r = _action(env, event_id="ev-grade-01", action="good",
                    session_id=s["session_id"], card_id="a1")
        assert r.status_code == 200
        body = r.json()
        assert body["schedule"]["review_count"] == 1
        assert body["session_remaining"] == 0
        assert body["session_completed"] is True
        assert json.loads(path.read_text())[0]["review_count"] == 1

    def test_again_resets_schedule(self, env):
        path = _write_cards(env.vault, "note-a", [
            _card("a1", interval=6, review_count=2)])
        s = _start_session(env)
        _action(env, event_id="ev-again-01", action="again",
                session_id=s["session_id"], card_id="a1")
        data = json.loads(path.read_text())[0]
        assert data["interval"] == 1
        assert data["review_count"] == 0

    def test_suspend_and_restore(self, env):
        _write_cards(env.vault, "note-a", [_card("a1"), _card("a2")])
        s = _start_session(env)
        r = _action(env, event_id="ev-susp-01", action="suspend",
                    session_id=s["session_id"], card_id="a1")
        assert r.json()["schedule"]["suspended"] is True
        # suspended 卡不再进入后续 session
        s2 = _start_session(env)
        assert {c["card_id"] for c in s2["cards"]} == {"a2"}
        # 本次会话撤销
        r2 = _action(env, event_id="ev-rest-01", action="restore",
                     session_id=s["session_id"], card_id="a1")
        assert r2.json()["schedule"]["suspended"] is False
        s3 = _start_session(env)
        assert {c["card_id"] for c in s3["cards"]} == {"a1", "a2"}

    def test_session_autocompletes_on_all_terminal(self, env):
        _write_cards(env.vault, "note-a", [_card("a1"), _card("a2")])
        s = _start_session(env)
        sid = s["session_id"]
        _action(env, event_id="ev-card-1", action="good", session_id=sid, card_id="a1")
        assert env.store.get_session(sid)["completed_at"] is None
        r = _action(env, event_id="ev-card-2", action="suspend", session_id=sid, card_id="a2")
        assert r.json()["session_completed"] is True
        assert env.store.get_session(sid)["completed_at"] is not None
        # restore 撤销终态 → 会话回到进行中
        _action(env, event_id="ev-card-3", action="restore", session_id=sid, card_id="a2")
        assert env.store.get_session(sid)["completed_at"] is None

    def test_abandoned_session_stays_incomplete(self, env):
        _write_cards(env.vault, "note-a", [_card("a1")])
        s = _start_session(env)
        # 打开后直接退出：completed_at 保持 null，是真实的未完成 session
        assert env.store.get_session(s["session_id"])["completed_at"] is None

    def test_open_source(self, env):
        (env.vault / "clips").mkdir()
        (env.vault / "clips" / "note-a.md").write_text("x", encoding="utf-8")
        _write_cards(env.vault, "note-a", [_card("a1", source_note="note-a.md")])
        s = _start_session(env)
        r = _action(env, event_id="ev-open-01", action="open_source",
                    session_id=s["session_id"], card_id="a1")
        body = r.json()
        assert body["source_available"] is True
        assert body["source_path"] == "clips/note-a.md"
        assert env.store.session_count() == 1  # 不额外创建 session

    def test_open_source_missing(self, env):
        _write_cards(env.vault, "note-a", [_card("a1", source_note="ghost.md")])
        s = _start_session(env)
        r = _action(env, event_id="ev-open-02", action="open_source",
                    session_id=s["session_id"], card_id="a1")
        assert r.status_code == 200
        assert r.json()["source_available"] is False


class TestActionErrors:
    def test_unknown_action(self, env):
        r = _action(env, event_id="ev-bad-0001", action="explode")
        assert r.status_code == 422

    def test_unknown_session(self, env):
        _write_cards(env.vault, "note-a", [_card("a1")])
        r = _action(env, event_id="ev-bad-0002", action="good",
                    session_id="nope", card_id="a1")
        assert r.status_code == 404

    def test_card_not_in_session(self, env):
        _write_cards(env.vault, "note-a", [_card("a1"), _card("other", next_review=NEXT_WEEK)])
        s = _start_session(env)
        r = _action(env, event_id="ev-bad-0003", action="good",
                    session_id=s["session_id"], card_id="other")
        assert r.status_code == 404

    def test_grade_requires_session_id(self, env):
        _write_cards(env.vault, "note-a", [_card("a1")])
        r = _action(env, event_id="ev-bad-0004", action="good", card_id="a1")
        assert r.status_code == 400

    def test_grade_requires_card_id(self, env):
        _write_cards(env.vault, "note-a", [_card("a1")])
        s = _start_session(env)
        r = _action(env, event_id="ev-bad-0005", action="good",
                    session_id=s["session_id"])
        assert r.status_code == 400

    def test_short_event_id_rejected(self, env):
        r = _action(env, event_id="x", action="impression")
        assert r.status_code == 422

    def test_restore_requires_suspended_card(self, env):
        # 对已评分（非 suspended）卡发 restore 必须被拒，否则会把已完成
        # session 错误地重新打开（Kimi finding）
        _write_cards(env.vault, "note-a", [_card("a1")])
        s = _start_session(env)
        _action(env, event_id="ev-rsq-0001", action="good",
                session_id=s["session_id"], card_id="a1")
        assert env.store.get_session(s["session_id"])["completed_at"] is not None
        r = _action(env, event_id="ev-rsq-0002", action="restore",
                    session_id=s["session_id"], card_id="a1")
        assert r.status_code == 409
        # session 保持已完成
        assert env.store.get_session(s["session_id"])["completed_at"] is not None


# ── 幂等与恢复 ──


class TestIdempotency:
    def test_replay_grade_no_double_advance(self, env):
        concepts = env.vault / "concepts"
        concepts.mkdir()
        (concepts / "know-x.md").write_text(
            f"---\nconfidence: 0.5\nlast_updated: {TODAY}\n---\n", encoding="utf-8")
        path = _write_cards(env.vault, "note-a", [_card("a1", concept="Know X")])
        s = _start_session(env)
        first = _action(env, event_id="ev-idem-01", action="good",
                        session_id=s["session_id"], card_id="a1")
        replay = _action(env, event_id="ev-idem-01", action="good",
                         session_id=s["session_id"], card_id="a1")
        assert replay.status_code == 200
        assert replay.json() == first.json()
        # 卡片只推进一次
        assert json.loads(path.read_text())[0]["review_count"] == 1
        # boost 只发生一次
        content = (concepts / "know-x.md").read_text(encoding="utf-8")
        conf = float(content.split("confidence: ")[1].split("\n")[0])
        event = env.store.get_event("ev-idem-01")
        expected = json.loads(event["boost_json"])["confidence"]
        assert conf == pytest.approx(expected)

    def test_replay_impression_no_duplicate(self, env):
        _write_cards(env.vault, "note-a", [_card("a1")])
        r1 = _action(env, event_id="ev-imp-dup1", action="impression")
        r2 = _action(env, event_id="ev-imp-dup1", action="impression")
        assert r1.json() == r2.json()
        with env.store._connect() as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM review_events WHERE event_id = 'ev-imp-dup1'"
            ).fetchone()[0]
        assert n == 1

    def test_event_id_cannot_be_reused_for_different_action(self, env):
        _write_cards(env.vault, "note-a", [_card("a1")])
        s = _start_session(env)
        first = _action(
            env, event_id="ev-bound-0001", action="good",
            session_id=s["session_id"], card_id="a1",
        )
        assert first.status_code == 200
        mismatch = _action(
            env, event_id="ev-bound-0001", action="easy",
            session_id=s["session_id"], card_id="a1",
        )
        assert mismatch.status_code == 409


class TestCrashRecovery:
    """两个崩溃窗口 + 状态漂移，都通过 service 层直接注入故障。"""

    def _session(self, env) -> dict:
        return create_review_session(
            env.vault, env.store, limit=5, entry_point="test")

    def test_pending_inserted_json_not_written(self, env, monkeypatch):
        # 窗口①：SQLite 已有 pending，apply（JSON 写入）崩溃
        path = _write_cards(env.vault, "note-a", [_card("a1")])
        s = self._session(env)

        def boom(*a, **k):
            raise OSError("simulated crash before JSON write")

        monkeypatch.setattr("neocortex.services.review_events.apply_outcome", boom)
        with pytest.raises(OSError):
            handle_review_action(
                env.vault, env.store, event_id="ev-crash-01", action="good",
                session_id=s["session_id"], card_id="a1")
        monkeypatch.undo()

        assert env.store.get_event("ev-crash-01")["status"] == "pending"
        assert json.loads(path.read_text())[0]["review_count"] == 0

        # 重试同一 event_id → 恢复：补 apply、标记 applied、返回响应
        resp = handle_review_action(
            env.vault, env.store, event_id="ev-crash-01", action="good",
            session_id=s["session_id"], card_id="a1")
        assert resp["schedule"]["review_count"] == 1
        assert env.store.get_event("ev-crash-01")["status"] == "applied"
        assert json.loads(path.read_text())[0]["review_count"] == 1

    def test_json_written_sqlite_commit_failed(self, env, monkeypatch):
        # 窗口②：JSON 已写、mark_applied（SQLite 最终提交）崩溃
        concepts = env.vault / "concepts"
        concepts.mkdir()
        (concepts / "know-x.md").write_text(
            f"---\nconfidence: 0.5\nlast_updated: {TODAY}\n---\n", encoding="utf-8")
        path = _write_cards(env.vault, "note-a", [_card("a1", concept="Know X")])
        s = self._session(env)

        original = ReviewEventStore.mark_applied

        def boom(self_, event_id, response):
            raise sqlite3.OperationalError("simulated commit failure")

        import sqlite3
        monkeypatch.setattr(ReviewEventStore, "mark_applied", boom)
        with pytest.raises(sqlite3.OperationalError):
            handle_review_action(
                env.vault, env.store, event_id="ev-crash-02", action="good",
                session_id=s["session_id"], card_id="a1")
        monkeypatch.setattr(ReviewEventStore, "mark_applied", original)

        # JSON 已推进，事件仍 pending
        assert json.loads(path.read_text())[0]["review_count"] == 1
        assert env.store.get_event("ev-crash-02")["status"] == "pending"
        confidence_after_crash = (concepts / "know-x.md").read_text(encoding="utf-8")

        # 重试 → 恢复路径重放 apply（绝对值赋值）→ applied；
        # 调度不二次推进、boost 不重复累加
        resp = handle_review_action(
            env.vault, env.store, event_id="ev-crash-02", action="good",
            session_id=s["session_id"], card_id="a1")
        assert resp["schedule"]["review_count"] == 1
        assert env.store.get_event("ev-crash-02")["status"] == "applied"
        assert json.loads(path.read_text())[0]["review_count"] == 1
        assert (concepts / "know-x.md").read_text(encoding="utf-8") == confidence_after_crash

    def test_pending_superseded_by_cli_marks_stale(self, env, monkeypatch):
        # 卡片在 pending 期间被其他写者（CLI）合法推进 → stale，不覆盖
        path = _write_cards(env.vault, "note-a", [_card("a1")])
        s = self._session(env)

        def boom(*a, **k):
            raise OSError("simulated crash")

        monkeypatch.setattr("neocortex.services.review_events.apply_outcome", boom)
        with pytest.raises(OSError):
            handle_review_action(
                env.vault, env.store, event_id="ev-crash-03", action="good",
                session_id=s["session_id"], card_id="a1")
        monkeypatch.undo()

        # CLI 在恢复前评了这张卡（easy → 状态 ≠ before ≠ after）
        grade_card(env.vault, "a1", 5)
        state_after_cli = json.loads(path.read_text())[0]

        with pytest.raises(ReviewFlowError) as exc_info:
            handle_review_action(
                env.vault, env.store, event_id="ev-crash-03", action="good",
                session_id=s["session_id"], card_id="a1")
        assert exc_info.value.status_code == 409
        assert env.store.get_event("ev-crash-03")["status"] == "stale"
        # 卡片状态保持 CLI 的结果，未被覆盖
        assert json.loads(path.read_text())[0] == state_after_cli
        # 对原 session 而言，该卡已被其他写者处理，是终态而非永久未完成。
        assert env.store.get_session(s["session_id"])["completed_at"] is not None

    def test_recovery_restores_session_consistency(self, env, monkeypatch):
        # 恢复后事件与卡片状态一致，session 完成态正确
        _write_cards(env.vault, "note-a", [_card("a1")])
        s = self._session(env)

        def boom(*a, **k):
            raise OSError("simulated crash")

        monkeypatch.setattr("neocortex.services.review_events.apply_outcome", boom)
        with pytest.raises(OSError):
            handle_review_action(
                env.vault, env.store, event_id="ev-crash-04", action="good",
                session_id=s["session_id"], card_id="a1")
        monkeypatch.undo()

        # 下一次 session 创建也会触发恢复
        create_review_session(env.vault, env.store, limit=5, entry_point="test")
        event = env.store.get_event("ev-crash-04")
        assert event["status"] == "applied"
        # 卡片状态与事件 after 快照一致
        from neocortex.services.review import find_stored_card, snapshot_schedule
        stored = find_stored_card(env.vault, "a1")
        assert snapshot_schedule(stored.card) == json.loads(event["after_json"])
        # 唯一 offered 卡已终态 → session 已完成
        assert env.store.get_session(s["session_id"])["completed_at"] is not None
