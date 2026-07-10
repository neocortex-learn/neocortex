"""Review session / event 存储与业务流（Slice 1）。

卡片状态在 vault JSON、事件在 data/neocortex.sqlite —— 跨存储一致性方案：

**pending/applied 状态机 + 绝对值快照。**

每次变更（grade/suspend/restore）按以下顺序执行，全程持有
:func:`neocortex.services.review.review_write_lock`（跨进程 flock）：

1. 锁内计算 :class:`ReviewOutcome`（before/after/concept-boost 都是**绝对
   目标值**，见 services/review.py 的幂等设计）；
2. ``INSERT review_events(status='pending', before/after/boost...)`` 并 commit
   —— SQLite 先成为"变更意图"的持久记录；
3. ``apply_outcome()``：把卡片 JSON 与 concept confidence **赋值**为 after
   （原子替换；重复执行 = 重复赋同样的值，无副作用）；
4. ``UPDATE status='applied', response_json=...`` 并 commit。

崩溃窗口与恢复（:func:`recover_pending_events`，在每次 session 创建和
action 处理前锁内执行）：

- **崩在 2↔3 之间**（SQLite 有 pending、JSON 尚未写）：卡片当前状态 ==
  before → 重放 apply → 标记 applied。
- **崩在 3↔4 之间**（JSON 已写、SQLite 最终提交失败）：卡片当前状态 ==
  after → 重放 apply 只是重复赋值（不会二次推进调度、不会二次 boost，
  boost 是绝对目标 confidence 而非增量）→ 标记 applied。
- **卡片状态既非 before 也非 after**：说明 pending 期间卡片被其他写者
  （如 CLI）合法推进过，事件标记 ``stale``，绝不覆盖新状态。

同一 ``event_id`` 重试：applied → 原样返回存储的 response_json，零副作用；
pending → 走恢复路径后返回。event_id 是 PRIMARY KEY，重复 INSERT 直接失败。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from neocortex.services.review import (
    CardNotFoundError,
    ReviewOutcome,
    apply_outcome,
    compute_outcome,
    find_stored_card,
    get_review_queue_summary,
    load_stored_cards,
    resolve_source_path,
    review_write_lock,
    select_session_cards,
    snapshot_schedule,
)

GRADE_ACTIONS = frozenset(["again", "hard", "good", "easy"])
CARD_ACTIONS = GRADE_ACTIONS | frozenset(["suspend", "restore"])
ALL_ACTIONS = CARD_ACTIONS | frozenset(["open_source", "impression"])

# 卡片在 session 内的终态动作。restore 会把 suspend 撤销 → 卡重新变为未终态。
_TERMINAL_ACTIONS = GRADE_ACTIONS | frozenset(["suspend"])


class ReviewFlowError(Exception):
    """业务错误 → HTTP 状态码。router 层负责转换。"""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ReviewEventStore:
    """data/neocortex.sqlite 里的 review_sessions / review_events 最小表。"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS review_sessions (
                    session_id TEXT PRIMARY KEY,
                    request_id TEXT,
                    entry_point TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    due_total INTEGER NOT NULL,
                    offered_count INTEGER NOT NULL,
                    offered_card_ids TEXT NOT NULL,
                    next_due_date TEXT,
                    response_json TEXT
                );
                CREATE TABLE IF NOT EXISTS review_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    card_id TEXT,
                    action TEXT NOT NULL,
                    due_total INTEGER,
                    storage_path TEXT,
                    before_json TEXT,
                    after_json TEXT,
                    boost_json TEXT,
                    status TEXT NOT NULL DEFAULT 'applied',
                    created_at TEXT NOT NULL,
                    applied_at TEXT,
                    response_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_review_events_session
                    ON review_events(session_id);
                """
            )
            # Additive migration for databases created by the first review MVP.
            # CREATE TABLE IF NOT EXISTS does not add columns to an existing table.
            session_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(review_sessions)")
            }
            for name, ddl in (
                ("request_id", "TEXT"),
                ("next_due_date", "TEXT"),
                ("response_json", "TEXT"),
            ):
                if name not in session_columns:
                    conn.execute(f"ALTER TABLE review_sessions ADD COLUMN {name} {ddl}")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_review_sessions_request_id"
                " ON review_sessions(request_id) WHERE request_id IS NOT NULL"
            )

    # ── sessions ──

    def create_session(
        self, session_id: str, entry_point: str, due_total: int,
        offered_card_ids: list[str], *, request_id: str | None = None,
        next_due_date: str | None = None,
    ) -> None:
        completed = _now() if not offered_card_ids else None
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO review_sessions"
                " (session_id, request_id, entry_point, started_at, completed_at,"
                "  due_total, offered_count, offered_card_ids, next_due_date)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id, request_id, entry_point, _now(), completed,
                    due_total, len(offered_card_ids), json.dumps(offered_card_ids),
                    next_due_date,
                ),
            )

    def get_session(self, session_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM review_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["offered_card_ids"] = json.loads(d["offered_card_ids"])
        return d

    def get_session_by_request_id(self, request_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM review_sessions WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["offered_card_ids"] = json.loads(d["offered_card_ids"])
        return d

    def set_session_response(self, session_id: str, response: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE review_sessions SET response_json = ? WHERE session_id = ?",
                (json.dumps(response, ensure_ascii=False), session_id),
            )

    def session_count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM review_sessions").fetchone()[0]

    def _terminal_card_ids(self, conn: sqlite3.Connection, session_id: str) -> set[str]:
        """session 内每张卡按最后一个 applied 的卡片动作判断终态。"""
        rows = conn.execute(
            "SELECT card_id, action, status FROM review_events"
            " WHERE session_id = ? AND status IN ('applied', 'stale')"
            " AND card_id IS NOT NULL"
            " ORDER BY rowid",
            (session_id,),
        ).fetchall()
        last: dict[str, tuple[str, str]] = {}
        for row in rows:
            if row["action"] in CARD_ACTIONS:
                last[row["card_id"]] = (row["action"], row["status"])
        return {
            cid
            for cid, (action, status) in last.items()
            if action in _TERMINAL_ACTIONS and status in ("applied", "stale")
        }

    def refresh_session_completion(self, session_id: str) -> tuple[bool, int]:
        """重算 completed_at。返回 (是否完成, 剩余未终态卡数)。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT offered_card_ids, completed_at FROM review_sessions"
                " WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return (False, 0)
            offered = set(json.loads(row["offered_card_ids"]))
            terminal = self._terminal_card_ids(conn, session_id)
            remaining = len(offered - terminal)
            done = bool(offered) and remaining == 0
            if done and row["completed_at"] is None:
                conn.execute(
                    "UPDATE review_sessions SET completed_at = ?"
                    " WHERE session_id = ?",
                    (_now(), session_id),
                )
            elif not done and row["completed_at"] is not None and offered:
                # restore 撤销了终态 → 会话重新变为进行中
                conn.execute(
                    "UPDATE review_sessions SET completed_at = NULL"
                    " WHERE session_id = ?",
                    (session_id,),
                )
            return (done, remaining)

    # ── events ──

    def get_event(self, event_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM review_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return dict(row) if row else None

    def insert_pending(
        self, event_id: str, session_id: str | None, card_id: str | None,
        action: str, due_total: int | None, outcome: ReviewOutcome,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO review_events"
                " (event_id, session_id, card_id, action, due_total,"
                "  storage_path, before_json, after_json, boost_json,"
                "  status, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (
                    event_id, session_id, card_id, action, due_total,
                    outcome.storage_path,
                    json.dumps(outcome.before),
                    json.dumps(outcome.after),
                    json.dumps(outcome.concept_boost) if outcome.concept_boost else None,
                    _now(),
                ),
            )

    def insert_applied(
        self, event_id: str, session_id: str | None, card_id: str | None,
        action: str, due_total: int | None, response: dict,
    ) -> None:
        """无卡片副作用的事件（impression / open_source）直接落 applied。"""
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO review_events"
                " (event_id, session_id, card_id, action, due_total,"
                "  status, created_at, applied_at, response_json)"
                " VALUES (?, ?, ?, ?, ?, 'applied', ?, ?, ?)",
                (
                    event_id, session_id, card_id, action, due_total,
                    now, now, json.dumps(response, ensure_ascii=False),
                ),
            )

    def mark_applied(self, event_id: str, response: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE review_events"
                " SET status = 'applied', applied_at = ?, response_json = ?"
                " WHERE event_id = ?",
                (_now(), json.dumps(response, ensure_ascii=False), event_id),
            )

    def mark_stale(self, event_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE review_events SET status = 'stale', applied_at = ?"
                " WHERE event_id = ?",
                (_now(), event_id),
            )

    def pending_events(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM review_events WHERE status = 'pending' ORDER BY rowid"
            ).fetchall()
        return [dict(r) for r in rows]


def _outcome_from_row(row: dict) -> ReviewOutcome:
    return ReviewOutcome(
        card_id=row["card_id"],
        storage_path=row["storage_path"],
        action=row["action"],
        quality=None,
        before=json.loads(row["before_json"]),
        after=json.loads(row["after_json"]),
        concept_boost=json.loads(row["boost_json"]) if row["boost_json"] else None,
    )


def _finalize_card_event(
    notes_dir: Path, store: ReviewEventStore, row: dict, response: dict,
) -> None:
    store.mark_applied(row["event_id"], response)
    if row["session_id"]:
        store.refresh_session_completion(row["session_id"])


def _mark_stale_and_refresh(store: ReviewEventStore, row: dict) -> None:
    """Stale grade/suspend means another writer already handled this card.

    It is terminal for the original offered session even though this event did
    not apply its own snapshot; otherwise the Mac UI can advance while the
    server permanently reports the session as incomplete.
    """
    store.mark_stale(row["event_id"])
    if row.get("session_id"):
        store.refresh_session_completion(row["session_id"])


def recover_pending_events(notes_dir: Path, store: ReviewEventStore) -> None:
    """崩溃恢复：调用方必须已持有 review_write_lock。"""
    for row in store.pending_events():
        outcome = _outcome_from_row(row)
        try:
            stored = find_stored_card(notes_dir, row["card_id"])
        except CardNotFoundError:
            _mark_stale_and_refresh(store, row)
            continue
        current = snapshot_schedule(stored.card)
        if current == outcome.after:
            # JSON 已写、SQLite 没来得及标记。仍要重放 apply：崩溃可能
            # 落在"卡片已写、boost 未写"的窗口，重放能补上 boost；
            # boost 是三态条件应用（见 _apply_concept_boost），不会覆盖
            # 期间其他写者（如 compiler）更新过的 confidence。
            apply_outcome(notes_dir, outcome)
            _finalize_card_event(
                notes_dir, store, row,
                _card_action_response(row, outcome, recovered=True),
            )
        elif current == outcome.before:
            # SQLite 有 pending、JSON 尚未写 —— 补 apply。
            apply_outcome(notes_dir, outcome)
            _finalize_card_event(
                notes_dir, store, row,
                _card_action_response(row, outcome, recovered=True),
            )
        else:
            # 卡片已被其他写者合法推进，不覆盖。
            _mark_stale_and_refresh(store, row)


def _card_action_response(
    row_or_ids: dict, outcome: ReviewOutcome, *, recovered: bool = False,
    session_remaining: int | None = None, session_completed: bool | None = None,
) -> dict:
    resp = {
        "event_id": row_or_ids["event_id"],
        "action": row_or_ids["action"],
        "card_id": outcome.card_id,
        "schedule": outcome.after,
    }
    if session_remaining is not None:
        resp["session_remaining"] = session_remaining
    if session_completed is not None:
        resp["session_completed"] = session_completed
    if recovered:
        resp["recovered"] = True
    return resp


# ── 业务流 ──

# GUI 档位 → SM-2 quality（有意折叠 0/1/2，见 services/review.py）。
from neocortex.services.review import GUI_QUALITY_MAP  # noqa: E402


def create_review_session(
    notes_dir: Path, store: ReviewEventStore, *, limit: int, entry_point: str,
    request_id: str | None = None,
) -> dict:
    """显式创建会话；``request_id`` 让超时重试返回同一个 session。

    菜单刷新 / daily / 预取禁止调用。内部调用未传 request_id 时生成一个，
    HTTP 契约则要求客户端提供稳定 UUID。
    """
    request_id = request_id or str(uuid.uuid4())
    with review_write_lock(notes_dir):
        recover_pending_events(notes_dir, store)
        existing = store.get_session_by_request_id(request_id)
        if existing is not None:
            if existing.get("response_json"):
                return json.loads(existing["response_json"])
            session = existing
        else:
            summary = get_review_queue_summary(notes_dir)
            selected = select_session_cards(summary, limit)
            session_id = str(uuid.uuid4())
            offered_card_ids = [s.card.id for s in selected]
            store.create_session(
                session_id, entry_point, summary.due_total, offered_card_ids,
                request_id=request_id, next_due_date=summary.next_due_date,
            )
            session = {
                "session_id": session_id,
                "due_total": summary.due_total,
                "offered_count": len(offered_card_ids),
                "offered_card_ids": offered_card_ids,
                "next_due_date": summary.next_due_date,
            }
    # source 解析是只读的且可能对旧卡做全 vault rglob（大 vault 上很慢），
    # 移到锁外执行，避免长时间阻塞其他写者。
    by_id = {s.card.id: s for s in load_stored_cards(notes_dir)}
    cards = []
    for card_id in session["offered_card_ids"]:
        s = by_id.get(card_id)
        if s is None:
            continue
        source_path = resolve_source_path(notes_dir, s.card.source_note)
        cards.append({
            "card_id": s.card.id,
            "question": s.card.question,
            "answer": s.card.answer,
            "concept": s.card.concept,
            "card_type": s.card.card_type,
            "source_path": source_path,
            "source_available": source_path is not None,
        })
    response = {
        "session_id": session["session_id"],
        "due_total": session["due_total"],
        "offered_count": len(cards),
        "next_due_date": session.get("next_due_date"),
        "cards": cards,
    }
    store.set_session_response(session["session_id"], response)
    return response


def handle_review_action(
    notes_dir: Path, store: ReviewEventStore, *,
    event_id: str, action: str,
    session_id: str | None = None, card_id: str | None = None,
) -> dict:
    """处理一次 review action。同一 event_id 重试幂等。"""
    if action not in ALL_ACTIONS:
        raise ReviewFlowError(422, f"unknown action {action!r}")

    with review_write_lock(notes_dir):
        # 幂等：先查 event_id
        existing = store.get_event(event_id)
        if existing is not None:
            if (
                existing["action"] != action
                or existing["session_id"] != session_id
                or existing["card_id"] != card_id
            ):
                raise ReviewFlowError(
                    409, "event_id already belongs to a different review action")
            if existing["status"] == "applied":
                if existing["response_json"]:
                    return json.loads(existing["response_json"])
                return {"event_id": event_id, "action": existing["action"], "replayed": True}
            if existing["status"] == "pending":
                recover_pending_events(notes_dir, store)
                refreshed = store.get_event(event_id)
                if refreshed and refreshed["status"] == "applied" and refreshed["response_json"]:
                    return json.loads(refreshed["response_json"])
                raise ReviewFlowError(
                    409, "event superseded by a newer card state; re-grade with a new event_id")
            raise ReviewFlowError(
                409, "event superseded by a newer card state; re-grade with a new event_id")

        recover_pending_events(notes_dir, store)

        if action == "impression":
            summary = get_review_queue_summary(notes_dir)
            response = {
                "event_id": event_id,
                "action": "impression",
                "due_total": summary.due_total,
                "next_due_date": summary.next_due_date,
            }
            store.insert_applied(
                event_id, session_id, card_id, "impression",
                summary.due_total, response,
            )
            return response

        # 其余 action 都作用于具体卡片
        if not card_id:
            raise ReviewFlowError(400, f"action {action!r} requires card_id")

        if action == "open_source":
            try:
                stored = find_stored_card(notes_dir, card_id)
            except CardNotFoundError:
                raise ReviewFlowError(404, f"card {card_id!r} not found") from None
            source_path = resolve_source_path(notes_dir, stored.card.source_note)
            response = {
                "event_id": event_id,
                "action": "open_source",
                "card_id": card_id,
                "source_path": source_path,
                "source_available": source_path is not None,
            }
            store.insert_applied(event_id, session_id, card_id, "open_source", None, response)
            return response

        # grade / suspend / restore：需要有效 session，且卡必须在 offered 列表里
        if not session_id:
            raise ReviewFlowError(400, f"action {action!r} requires session_id")
        session = store.get_session(session_id)
        if session is None:
            raise ReviewFlowError(404, f"session {session_id!r} not found")
        if card_id not in session["offered_card_ids"]:
            raise ReviewFlowError(404, f"card {card_id!r} not offered in this session")
        try:
            stored = find_stored_card(notes_dir, card_id)
        except CardNotFoundError:
            raise ReviewFlowError(404, f"card {card_id!r} not found") from None

        if action in GRADE_ACTIONS:
            outcome = compute_outcome(
                notes_dir, stored, "grade", quality=GUI_QUALITY_MAP[action])
        elif action == "suspend":
            outcome = compute_outcome(notes_dir, stored, "suspend")
        else:  # restore
            # 前置校验：只允许撤销确实处于 suspended 的卡。否则对已评分卡
            # 发 restore 会把它移出终态集合、错误地重新打开已完成 session。
            if not stored.card.suspended:
                raise ReviewFlowError(409, f"card {card_id!r} is not suspended")
            outcome = compute_outcome(notes_dir, stored, "restore")

        # ①意图落 SQLite（pending）→ ②幂等 apply → ③标记 applied
        store.insert_pending(event_id, session_id, card_id, action,
                             session["due_total"], outcome)
        apply_outcome(notes_dir, outcome)
        completed, remaining = _session_state_after(store, session_id, card_id, action)
        response = _card_action_response(
            {"event_id": event_id, "action": action}, outcome,
            session_remaining=remaining, session_completed=completed,
        )
        store.mark_applied(event_id, response)
        store.refresh_session_completion(session_id)
        return response


def _session_state_after(
    store: ReviewEventStore, session_id: str, card_id: str, action: str,
) -> tuple[bool, int]:
    """计算本次 action 落地后的 session 完成态（事件此刻仍是 pending，
    手动把当前卡计入/移出终态集合）。"""
    session = store.get_session(session_id)
    offered = set(session["offered_card_ids"])
    with store._connect() as conn:
        terminal = store._terminal_card_ids(conn, session_id)
    if action in _TERMINAL_ACTIONS:
        terminal.add(card_id)
    elif action == "restore":
        terminal.discard(card_id)
    remaining = len(offered - terminal)
    return (bool(offered) and remaining == 0, remaining)
