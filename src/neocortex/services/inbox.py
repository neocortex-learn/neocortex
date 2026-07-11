"""P0 Inbox terminal actions with SQLite-backed idempotency and undo."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

import fcntl

from neocortex.models import Clip, InboxActionResponse, InboxItem, InboxListResponse

TERMINAL_ACTIONS = frozenset({"keep", "skip", "later", "master"})
ALL_ACTIONS = TERMINAL_ACTIONS | frozenset({"undo"})
ACTION_STATUS = {
    "keep": "reference",
    "skip": "archived",
    "later": "later",
    "master": "promoted",
}


class InboxFlowError(Exception):
    """Business error translated to an HTTP response by the route layer."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class StoredClip:
    path: Path
    clip: Clip


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_stored_clips(notes_dir: Path) -> list[StoredClip]:
    """Load clips together with their actual paths; never reconstruct filenames."""
    from neocortex.config import _parse_clip_file

    clips_dir = notes_dir / "clips"
    if not clips_dir.exists():
        return []
    stored: list[StoredClip] = []
    for path in sorted(clips_dir.rglob("*.md")):
        clip = _parse_clip_file(path)
        if clip is not None:
            stored.append(StoredClip(path=path, clip=clip))
    return stored


def find_stored_clip(notes_dir: Path, clip_id: str) -> StoredClip:
    matches = [stored for stored in load_stored_clips(notes_dir) if stored.clip.id == clip_id]
    if not matches:
        raise InboxFlowError(404, f"clip {clip_id!r} not found")
    if len(matches) > 1:
        raise InboxFlowError(409, f"clip id {clip_id!r} is not unique")
    return matches[0]


def _to_item(stored: StoredClip) -> InboxItem:
    clip = stored.clip
    return InboxItem(
        clip_id=clip.id,
        saved_path=str(stored.path),
        source=clip.source,
        title=clip.title,
        summary=clip.summary,
        status=clip.status,
        created_at=clip.created_at,
        next_surface=clip.next_surface,
        related_concepts=list(clip.related_concepts),
    )


def list_inbox(notes_dir: Path) -> InboxListResponse:
    items = [
        _to_item(stored)
        for stored in load_stored_clips(notes_dir)
        if stored.clip.status == "inbox"
    ]
    items.sort(key=lambda item: (item.created_at, item.clip_id), reverse=True)
    return InboxListResponse(items=items, total=len(items))


def _snapshot(path: Path) -> dict[str, str | None]:
    from neocortex.config import _parse_clip_file

    clip = _parse_clip_file(path)
    if clip is None:
        raise InboxFlowError(409, f"clip file {path} is no longer parseable")
    return {
        "status": clip.status,
        "processed_at": clip.processed_at,
        "promoted_to": clip.promoted_to,
    }


def update_clip_frontmatter(path: Path, fields: dict[str, object]) -> None:
    """Atomically patch named frontmatter keys in the exact existing file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InboxFlowError(409, f"cannot read clip file {path}") from exc
    if not text.startswith("---\n"):
        raise InboxFlowError(409, f"clip file {path} has no frontmatter")
    closing = text.find("\n---", 4)
    if closing < 0:
        raise InboxFlowError(409, f"clip file {path} has invalid frontmatter")

    frontmatter = text[4:closing]
    lines = frontmatter.splitlines()
    for key, value in fields.items():
        rendered = "" if value is None else str(value)
        replacement = f"{key}: {rendered}"
        for index, line in enumerate(lines):
            if line.partition(":")[0].strip() == key:
                lines[index] = replacement
                break
        else:
            lines.append(replacement)
    updated = "---\n" + "\n".join(lines) + text[closing:]

    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(updated)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


@contextmanager
def inbox_write_lock(store: "InboxEventStore") -> Iterator[None]:
    """Serialize SQLite intent and clip-file replacement across processes."""
    lock_path = store.db_path.with_name("inbox-events.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class InboxEventStore:
    """Minimal independent event table inside ``data/neocortex.sqlite``."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS inbox_events (
                    action_id TEXT PRIMARY KEY,
                    clip_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_action_id TEXT,
                    storage_path TEXT NOT NULL,
                    before_json TEXT NOT NULL,
                    after_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    applied_at TEXT,
                    response_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_inbox_events_clip
                    ON inbox_events(clip_id);
                """
            )

    def get_event(self, action_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT rowid AS event_rowid, * FROM inbox_events WHERE action_id = ?",
                (action_id,),
            ).fetchone()
        return dict(row) if row else None

    def insert_pending(
        self, *, action_id: str, clip_id: str, action: str,
        target_action_id: str | None, storage_path: str,
        before: dict, after: dict,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO inbox_events"
                " (action_id, clip_id, action, target_action_id, storage_path,"
                "  before_json, after_json, status, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (
                    action_id, clip_id, action, target_action_id, storage_path,
                    json.dumps(before, ensure_ascii=False),
                    json.dumps(after, ensure_ascii=False), _now(),
                ),
            )

    def mark_applied(self, action_id: str, response: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE inbox_events SET status = 'applied', applied_at = ?,"
                " response_json = ? WHERE action_id = ?",
                (_now(), json.dumps(response, ensure_ascii=False), action_id),
            )

    def mark_stale(self, action_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE inbox_events SET status = 'stale', applied_at = ?"
                " WHERE action_id = ?",
                (_now(), action_id),
            )

    def pending_events(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT rowid AS event_rowid, * FROM inbox_events"
                " WHERE status = 'pending' ORDER BY rowid"
            ).fetchall()
        return [dict(row) for row in rows]

    def has_later_applied_event(self, target: dict) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM inbox_events WHERE clip_id = ? AND rowid > ?"
                " AND status = 'applied' LIMIT 1",
                (target["clip_id"], target["event_rowid"]),
            ).fetchone()
        return row is not None


def _event_path(notes_dir: Path, storage_path: str) -> Path:
    path = (notes_dir / storage_path).resolve()
    clips_root = (notes_dir / "clips").resolve()
    if not path.is_relative_to(clips_root):
        raise InboxFlowError(409, "stored clip path escapes the vault clips directory")
    return path


def _response(
    row: dict, path: Path, after: dict, *, recovered: bool = False,
) -> dict:
    return InboxActionResponse(
        action_id=row["action_id"],
        clip_id=row["clip_id"],
        action=row["action"],
        status=str(after["status"]),
        saved_path=str(path),
        undone_action_id=row.get("target_action_id"),
        recovered=recovered,
    ).model_dump(mode="json")


def recover_pending_events(notes_dir: Path, store: InboxEventStore) -> None:
    """Replay absolute frontmatter snapshots; never overwrite newer clip state."""
    for row in store.pending_events():
        path = _event_path(notes_dir, row["storage_path"])
        if not path.exists():
            store.mark_stale(row["action_id"])
            continue
        before = json.loads(row["before_json"])
        after = json.loads(row["after_json"])
        current = _snapshot(path)
        if current == before:
            update_clip_frontmatter(path, after)
        elif current != after:
            store.mark_stale(row["action_id"])
            continue
        store.mark_applied(row["action_id"], _response(row, path, after, recovered=True))


def handle_inbox_action(
    notes_dir: Path, store: InboxEventStore, *, action_id: str,
    clip_id: str, action: str, target_action_id: str | None = None,
) -> InboxActionResponse:
    """Apply one terminal action or undo a specified action, idempotently."""
    if action not in ALL_ACTIONS:
        raise InboxFlowError(422, f"unknown action {action!r}")
    if action == "undo" and not target_action_id:
        raise InboxFlowError(400, "undo requires target_action_id")
    if action != "undo" and target_action_id is not None:
        raise InboxFlowError(400, f"action {action!r} must not include target_action_id")

    with inbox_write_lock(store):
        existing = store.get_event(action_id)
        if existing is not None:
            if (
                existing["clip_id"] != clip_id
                or existing["action"] != action
                or existing["target_action_id"] != target_action_id
            ):
                raise InboxFlowError(409, "action_id already belongs to a different inbox action")
            if existing["status"] == "applied" and existing["response_json"]:
                return InboxActionResponse.model_validate_json(existing["response_json"])
            if existing["status"] == "pending":
                recover_pending_events(notes_dir, store)
                refreshed = store.get_event(action_id)
                if refreshed and refreshed["status"] == "applied" and refreshed["response_json"]:
                    return InboxActionResponse.model_validate_json(refreshed["response_json"])
            raise InboxFlowError(409, "inbox action was superseded by a newer clip state")

        recover_pending_events(notes_dir, store)
        stored = find_stored_clip(notes_dir, clip_id)
        before = _snapshot(stored.path)

        if action == "undo":
            target = store.get_event(target_action_id or "")
            if (
                target is None
                or target["clip_id"] != clip_id
                or target["action"] not in TERMINAL_ACTIONS
                or target["status"] != "applied"
            ):
                raise InboxFlowError(404, "undo target is not an applied action for this clip")
            if store.has_later_applied_event(target) or before != json.loads(target["after_json"]):
                raise InboxFlowError(409, "undo target is stale because the clip has a newer action")
            after = json.loads(target["before_json"])
        else:
            if before["status"] != "inbox":
                raise InboxFlowError(409, f"clip {clip_id!r} is already {before['status']!r}")
            after = dict(before)
            after["status"] = ACTION_STATUS[action]
            after["processed_at"] = date.today().isoformat()
            after["promoted_to"] = stored.clip.source if action == "master" else None

        storage_path = str(stored.path.relative_to(notes_dir))
        store.insert_pending(
            action_id=action_id, clip_id=clip_id, action=action,
            target_action_id=target_action_id, storage_path=storage_path,
            before=before, after=after,
        )
        update_clip_frontmatter(stored.path, after)
        row = store.get_event(action_id)
        assert row is not None
        response = _response(row, stored.path, after)
        store.mark_applied(action_id, response)
        return InboxActionResponse.model_validate(response)
