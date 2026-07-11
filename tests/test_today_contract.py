"""Focused P0 Today/Inbox/Top of Mind contract tests."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from neocortex.config import _parse_clip_file, save_clip
from neocortex.models import Clip

TOKEN = "test-token-1234567890"
PORT = 8765
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    data = tmp_path / "data"
    vault.mkdir()
    data.mkdir()
    monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: vault)
    monkeypatch.setattr("neocortex.config.get_data_dir", lambda: data)

    from neocortex.server.app import create_app

    client = TestClient(app=create_app(TOKEN, PORT), base_url=f"http://127.0.0.1:{PORT}")
    return SimpleNamespace(vault=vault, data=data, client=client)


def _stored_clip(vault: Path, clip_id: str, *, status: str = "inbox", **kwargs) -> Path:
    created = kwargs.pop("created_at", (date.today() - timedelta(days=7)).isoformat())
    path = save_clip(vault, Clip(
        id=clip_id,
        source=kwargs.pop("source", f"https://example.com/{clip_id}"),
        content=kwargs.pop("content", f"body {clip_id}"),
        title=kwargs.pop("title", f"Title {clip_id}"),
        summary=kwargs.pop("summary", ""),
        status=status,
        created_at=created,
        next_surface=kwargs.pop("next_surface", date.today().isoformat()),
        related_concepts=kwargs.pop("related_concepts", []),
        topic=kwargs.pop("topic", "general"),
        **kwargs,
    ))
    return path


def _action(env, action_id: str, clip_id: str, action: str, **extra):
    return env.client.post(
        "/api/inbox/action",
        json={"action_id": action_id, "clip_id": clip_id, "action": action, **extra},
        headers=AUTH,
    )


class TestInboxActions:
    @pytest.mark.parametrize(
        ("action", "expected_status"),
        [("keep", "reference"), ("skip", "archived"),
         ("later", "later"), ("master", "promoted")],
    )
    def test_four_terminal_actions(self, env, action, expected_status):
        path = _stored_clip(env.vault, action)
        response = _action(env, f"action-{action}-0001", action, action)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == expected_status
        assert _parse_clip_file(path).status == expected_status

    def test_action_id_replay_is_identical_and_writes_one_event(self, env):
        path = _stored_clip(env.vault, "replay")
        request_id = "action-replay-0001"
        first = _action(env, request_id, "replay", "keep")
        replay = _action(env, request_id, "replay", "keep")
        assert first.status_code == replay.status_code == 200
        assert replay.json() == first.json()
        assert _parse_clip_file(path).status == "reference"
        with sqlite3.connect(env.data / "neocortex.sqlite") as conn:
            assert conn.execute("SELECT COUNT(*) FROM inbox_events").fetchone()[0] == 1

    @pytest.mark.parametrize("file_already_updated", [False, True])
    def test_pending_event_recovers_both_crash_windows(self, env, file_already_updated):
        from neocortex.services.inbox import (
            InboxEventStore,
            handle_inbox_action,
            update_clip_frontmatter,
        )

        path = _stored_clip(env.vault, "recover")
        store = InboxEventStore(env.data / "neocortex.sqlite")
        before = {"status": "inbox", "processed_at": None, "promoted_to": None}
        after = {
            "status": "reference",
            "processed_at": date.today().isoformat(),
            "promoted_to": None,
        }
        store.insert_pending(
            action_id="action-recover-0001", clip_id="recover", action="keep",
            target_action_id=None, storage_path=str(path.relative_to(env.vault)),
            before=before, after=after,
        )
        if file_already_updated:
            update_clip_frontmatter(path, after)

        response = handle_inbox_action(
            env.vault, store, action_id="action-recover-0001",
            clip_id="recover", action="keep",
        )
        assert response.recovered is True
        assert _parse_clip_file(path).status == "reference"
        assert store.get_event("action-recover-0001")["status"] == "applied"

    def test_updates_actual_legacy_path_without_creating_duplicate(self, env):
        generated = _stored_clip(env.vault, "legacy", title="Renamed Later")
        legacy = generated.with_name("hand-renamed-original.md")
        generated.rename(legacy)
        before = set((env.vault / "clips").rglob("*.md"))

        response = _action(env, "action-legacy-0001", "legacy", "later")

        assert response.status_code == 200, response.text
        assert response.json()["saved_path"] == str(legacy)
        assert _parse_clip_file(legacy).status == "later"
        assert set((env.vault / "clips").rglob("*.md")) == before

    def test_undo_restores_before_state_and_rejects_stale_target(self, env):
        path = _stored_clip(env.vault, "undo")
        applied = _action(env, "action-keep-0001", "undo", "keep")
        assert applied.status_code == 200
        undone = _action(
            env, "action-undo-0001", "undo", "undo",
            target_action_id="action-keep-0001",
        )
        assert undone.status_code == 200, undone.text
        assert undone.json()["status"] == "inbox"
        assert _parse_clip_file(path).status == "inbox"

        assert _action(env, "action-skip-0001", "undo", "skip").status_code == 200
        stale = _action(
            env, "action-undo-0002", "undo", "undo",
            target_action_id="action-keep-0001",
        )
        assert stale.status_code == 409
        assert _parse_clip_file(path).status == "archived"

    def test_list_only_returns_undecided_inbox(self, env):
        _stored_clip(env.vault, "inbox")
        _stored_clip(env.vault, "kept", status="reference")
        response = env.client.get("/api/inbox", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert [item["clip_id"] for item in response.json()["items"]] == ["inbox"]


class TestTodayContract:
    def test_limit_total_continue_read_and_explainable_order(self, env):
        for index in range(5):
            _stored_clip(
                env.vault, f"due-{index}", title=f"General {index}",
                created_at=(date.today() - timedelta(days=10 - index)).isoformat(),
            )
        _stored_clip(
            env.vault, "focus", title="SQLite WAL notes",
            created_at=date.today().isoformat(),
        )
        _stored_clip(env.vault, "kept", status="reference", title="SQLite kept")
        _stored_clip(env.vault, "later", status="later", title="Continue this")

        put = env.client.put(
            "/api/top-of-mind", json={"topics": ["SQLite"]}, headers=AUTH,
        )
        assert put.status_code == 200, put.text
        response = env.client.get("/api/daily", headers=AUTH)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["surfacing_total"] == 6
        assert len(body["surfacing"]) == 3
        assert body["surfacing"][0]["clip_id"] == "focus"
        assert body["surfacing"][0]["priority_reason"] == "Top of Mind: SQLite"
        assert all(item["clip_id"] != "kept" for item in body["surfacing"])
        assert body["continue_read"]["clip_id"] == "later"
        assert body["top_of_mind"] == ["SQLite"]


class TestTopOfMind:
    def test_trim_deduplicate_persist_and_replay(self, env):
        import json

        payload = {"topics": ["  SQLite  ", "sqlite", "Agent   loops", ""]}
        first = env.client.put("/api/top-of-mind", json=payload, headers=AUTH)
        replay = env.client.put("/api/top-of-mind", json=payload, headers=AUTH)
        assert first.status_code == replay.status_code == 200
        assert first.json() == replay.json() == {"topics": ["SQLite", "Agent loops"]}
        readback = env.client.get("/api/top-of-mind", headers=AUTH)
        assert readback.json() == first.json()
        saved = json.loads((env.data / "config.json").read_text(encoding="utf-8"))
        assert saved["output_settings"]["notes_dir"] == str(env.vault)

    def test_rejects_more_than_three_unique_topics(self, env):
        response = env.client.put(
            "/api/top-of-mind",
            json={"topics": ["one", "two", "three", "four"]},
            headers=AUTH,
        )
        assert response.status_code == 422


class TestSecurity:
    def test_inbox_requires_auth(self, env):
        assert env.client.get("/api/inbox").status_code == 401

    def test_mutation_requires_json_content_type(self, env):
        response = env.client.post(
            "/api/inbox/action",
            content="action=keep",
            headers={**AUTH, "Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 415
