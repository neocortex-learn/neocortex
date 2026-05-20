"""Server security tests (Sprint 0 S0-2 + S0-3)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


TOKEN = "test-token-1234567890"
PORT = 8765
EXPECTED_HOST = f"127.0.0.1:{PORT}"


@pytest.fixture
def client():
    """Build a TestClient against a fresh app instance with known token/port."""
    from neocortex.server.app import create_app

    app = create_app(token=TOKEN, port=PORT)
    # TestClient by default sends Host="testserver"; override to match.
    return TestClient(app, base_url=f"http://{EXPECTED_HOST}")


class TestHealthzUnauthenticated:
    def test_healthz_no_auth(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_healthz_no_cors_header(self, client):
        """Defense in depth: no CORS even on public endpoint."""
        r = client.get("/healthz")
        assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


class TestTokenAuth:
    def test_protected_endpoint_no_token(self, client):
        r = client.get("/api/version")
        assert r.status_code == 401

    def test_protected_endpoint_wrong_token(self, client):
        r = client.get(
            "/api/version",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert r.status_code == 401

    def test_protected_endpoint_malformed_auth(self, client):
        r = client.get(
            "/api/version",
            headers={"Authorization": "NotBearer token"},
        )
        assert r.status_code == 401

    def test_protected_endpoint_correct_token(self, client):
        r = client.get(
            "/api/version",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert r.status_code == 200
        assert "version" in r.json()


class TestHostHeaderCheck:
    def test_wrong_host_rejected(self, client):
        # Override the per-request Host header
        r = client.get(
            "/healthz",
            headers={"Host": "evil.com"},
        )
        assert r.status_code == 400
        assert "host" in r.text.lower()

    def test_localhost_alias_accepted(self, client):
        r = client.get(
            "/healthz",
            headers={"Host": f"localhost:{PORT}"},
        )
        assert r.status_code == 200


class TestOriginCheck:
    def test_no_origin_header_ok(self, client):
        """SwiftUI URLSession sends no Origin header by default — allowed."""
        r = client.get(
            "/api/version",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert r.status_code == 200

    def test_bad_origin_rejected(self, client):
        r = client.get(
            "/api/version",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Origin": "https://evil.com",
            },
        )
        assert r.status_code == 403

    def test_null_origin_allowed(self, client):
        """file:// pages send Origin: null."""
        r = client.get(
            "/api/version",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Origin": "null",
            },
        )
        assert r.status_code == 200


class TestContentTypeCheck:
    def test_post_without_json_content_type_rejected(self, client):
        r = client.post(
            "/api/version",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data="foo=bar",
        )
        # /api/version isn't a POST endpoint but middleware fires before routing
        assert r.status_code == 415


class TestClipEndpoint:
    """POST /api/clip — wraps services.clip.clip_text (S0-4)."""

    def test_clip_no_auth(self, client):
        r = client.post(
            "/api/clip",
            headers={"Content-Type": "application/json"},
            json={"source": "test"},
        )
        assert r.status_code == 401

    def test_clip_missing_source(self, client):
        r = client.post(
            "/api/clip",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json={},
        )
        assert r.status_code == 422

    def test_clip_plain_text(self, client, tmp_path, monkeypatch):
        """End-to-end: POST plain text → ClipResult JSON, file saved."""
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)

        r = client.post(
            "/api/clip",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json={"source": "服务器端 clip 测试，无 LLM key 走 skip 路径", "process": False},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["aborted"] is False
        assert body["llm_status"] == "skipped_user_opt_out"
        assert body["saved_path"] != ""
        # Real file written to the patched notes_dir
        from pathlib import Path
        assert Path(body["saved_path"]).exists()
        assert body["clip"]["title"] != ""

    def test_clip_returns_full_result_shape(self, client, tmp_path, monkeypatch):
        """Response must conform to ClipResult schema so SwiftUI/GUI can rely on it."""
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)

        r = client.post(
            "/api/clip",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json={"source": "schema shape test", "process": False},
        )
        assert r.status_code == 200
        body = r.json()
        for key in (
            "saved_path", "clip", "llm_status", "llm_error",
            "existing_cluster_delta", "new_or_pending_clusters",
            "related_notes", "aborted", "abort_reason",
        ):
            assert key in body, f"ClipResult missing field {key}"


class TestDeleteNoteEndpoint:
    """POST /api/notes/delete — trash a note + reverse concept refs."""

    def test_delete_no_auth(self, client):
        r = client.post(
            "/api/notes/delete",
            headers={"Content-Type": "application/json"},
            json={"path": "x.md"},
        )
        assert r.status_code == 401

    def test_delete_nonexistent(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)
        r = client.post(
            "/api/notes/delete",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json={"path": "does-not-exist.md"},
        )
        assert r.status_code == 404

    def test_delete_path_escape_rejected(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)
        # Create a file outside the vault
        outside = tmp_path.parent / "outside.md"
        outside.write_text("---\nid: x\n---\nbody", encoding="utf-8")
        try:
            r = client.post(
                "/api/notes/delete",
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "Content-Type": "application/json",
                },
                json={"path": str(outside)},
            )
            assert r.status_code == 400
            assert outside.exists(), "outside-vault file must NOT be deleted"
        finally:
            if outside.exists():
                outside.unlink()

    def test_delete_clip_reverses_concept_ec(self, client, tmp_path, monkeypatch):
        """Real flow: trashing a clip with related_concepts decrements
        the corresponding concept page evidence_count."""
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)

        # Set up: a concept page that references our clip
        concepts = tmp_path / "concepts"
        concepts.mkdir()
        (concepts / "transformer.md").write_text(
            "---\nevidence_count: 5\nsource_notes: [\"clip:abc\"]\n---\nbody\n",
            encoding="utf-8",
        )
        # Set up: the clip itself
        clips = tmp_path / "clips"
        clips.mkdir()
        clip_file = clips / "2026-05-20-test.md"
        clip_file.write_text(
            "---\nid: abc\nrelated_concepts: [\"Transformer\"]\n---\nbody\n",
            encoding="utf-8",
        )

        r = client.post(
            "/api/notes/delete",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json={"path": str(clip_file)},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "Transformer" in body["reversed_concepts"]
        # Concept page evidence_count decremented
        updated = (concepts / "transformer.md").read_text(encoding="utf-8")
        assert "evidence_count: 4" in updated
        # And the clip:abc reference is gone
        assert "clip:abc" not in updated


class TestRuntimeFiles:
    def test_provision_writes_files(self, tmp_path, monkeypatch):
        """runtime.provision_runtime writes pid/port/token to ~/.neocortex/."""
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        from neocortex.server.runtime import (
            cleanup_runtime,
            provision_runtime,
            read_port,
            read_token,
        )

        try:
            secrets = provision_runtime(port=12345)
            assert (tmp_path / "server.pid").exists()
            assert (tmp_path / "server.port").read_text() == "12345"
            assert (tmp_path / "server-token").read_text() == secrets.token
            assert read_token() == secrets.token
            assert read_port() == 12345

            # 0600 permissions
            import os
            mode = os.stat(tmp_path / "server-token").st_mode & 0o777
            assert mode == 0o600
        finally:
            cleanup_runtime()
            assert not (tmp_path / "server.pid").exists()
            assert not (tmp_path / "server-token").exists()

    def test_provision_tightens_existing_token_permissions(self, tmp_path, monkeypatch):
        """An old loose-permission token file must be made 0600 before reuse."""
        import os

        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        token_path = tmp_path / "server-token"
        token_path.write_text("old-token", encoding="utf-8")
        os.chmod(token_path, 0o644)

        from neocortex.server.runtime import cleanup_runtime, provision_runtime

        try:
            secrets = provision_runtime(port=12346)
            assert token_path.read_text(encoding="utf-8") == secrets.token
            mode = os.stat(token_path).st_mode & 0o777
            assert mode == 0o600
        finally:
            cleanup_runtime()
