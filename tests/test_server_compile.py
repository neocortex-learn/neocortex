"""Tests for POST /api/compile + GET /api/compile/status (start-then-poll)."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from neocortex.models import AppConfig, CompileResult, OutputSettings, ProviderType

TOKEN = "test-token-1234567890"
PORT = 8765
EXPECTED_HOST = f"127.0.0.1:{PORT}"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client():
    from neocortex.server.app import create_app

    app = create_app(token=TOKEN, port=PORT)
    with TestClient(app, base_url=f"http://{EXPECTED_HOST}") as c:
        yield c


def _configured() -> AppConfig:
    return AppConfig(
        provider=ProviderType.CLAUDE,
        api_key="sk-test",
        output_settings=OutputSettings(),
    )


def _poll_until_terminal(client, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get("/api/compile/status", headers=AUTH).json()
        if body["state"] in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"compile job did not finish in {timeout}s: {body}")


class TestAuth:
    def test_post_requires_token(self, client):
        r = client.post("/api/compile", json={})
        assert r.status_code == 401

    def test_status_requires_token(self, client):
        r = client.get("/api/compile/status")
        assert r.status_code == 401


class TestStartValidation:
    def test_unconfigured_llm_is_400_and_no_job(self, client):
        with patch("neocortex.config.load_config", return_value=AppConfig()):
            r = client.post("/api/compile", json={}, headers=AUTH)
        assert r.status_code == 400
        assert "未配置" in r.json()["detail"]
        status = client.get("/api/compile/status", headers=AUTH).json()
        assert status["state"] == "idle"

    def test_initial_status_is_idle(self, client):
        body = client.get("/api/compile/status", headers=AUTH).json()
        assert body["state"] == "idle"
        assert body["result"] is None


class TestJobLifecycle:
    def test_success_flow_reports_progress_and_result(self, client):
        async def fake_compile(*, on_progress=None, **kwargs):
            if on_progress:
                on_progress(2, 5)
            await asyncio.sleep(0.3)
            return CompileResult(
                notes_processed=5,
                concepts_created=2,
                concepts_updated=1,
                wikilinks_inserted=4,
            )

        with (
            patch("neocortex.config.load_config", return_value=_configured()),
            patch("neocortex.services.compile.compile_notes", side_effect=fake_compile),
        ):
            r = client.post("/api/compile", json={"force": True}, headers=AUTH)
            assert r.status_code == 200
            started = r.json()
            assert started["accepted"] is True
            assert started["state"] == "running"
            assert started["force"] is True
            assert started["started_at"]

            # Second POST while running must not start a new job.
            r2 = client.post("/api/compile", json={}, headers=AUTH)
            assert r2.json()["accepted"] is False
            assert r2.json()["state"] == "running"

            final = _poll_until_terminal(client)

        assert final["state"] == "done"
        assert final["current"] == 2 and final["total"] == 5
        assert final["finished_at"]
        assert final["result"]["notes_processed"] == 5
        assert final["result"]["concepts_created"] == 2
        assert final["error"] is None

    def test_failure_is_visible_in_status(self, client):
        async def boom(**kwargs):
            raise RuntimeError("LLM exploded")

        with (
            patch("neocortex.config.load_config", return_value=_configured()),
            patch("neocortex.services.compile.compile_notes", side_effect=boom),
        ):
            r = client.post("/api/compile", json={}, headers=AUTH)
            assert r.json()["accepted"] is True
            final = _poll_until_terminal(client)

        assert final["state"] == "failed"
        assert "RuntimeError" in final["error"]
        assert "LLM exploded" in final["error"]
        assert final["result"] is None

    def test_restart_after_done_starts_fresh_job(self, client):
        async def quick(**kwargs):
            return CompileResult(notes_processed=1)

        with (
            patch("neocortex.config.load_config", return_value=_configured()),
            patch("neocortex.services.compile.compile_notes", side_effect=quick),
        ):
            client.post("/api/compile", json={}, headers=AUTH)
            _poll_until_terminal(client)

            r = client.post("/api/compile", json={}, headers=AUTH)
            assert r.json()["accepted"] is True
            final = _poll_until_terminal(client)
            assert final["state"] == "done"
