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


class TestClipDedup:
    """Same URL clipped twice → second call returns the original note path
    with ``reused=true`` instead of writing a second file."""

    def test_same_url_returns_existing(self, client, tmp_path, monkeypatch):

        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)

        # Seed an existing clip with a known URL in its frontmatter.
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()
        seed = clips_dir / "2026-05-22-seed.md"
        seed.write_text(
            '---\n'
            'title: "Original"\n'
            'source: "https://overreacted.io/before-you-memo/"\n'
            'date: 2026-05-20\n'
            '---\n\nbody',
            encoding="utf-8",
        )

        r = client.post(
            "/api/clip",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "source": "https://overreacted.io/before-you-memo/?utm_source=fb",
                "process": False,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["reused"] is True
        assert body["saved_path"] == str(seed)
        assert body["clip"]["title"] == "Original"
        # No new file written.
        siblings = list(clips_dir.glob("*.md"))
        assert siblings == [seed]

    def test_text_clip_not_deduped(self, client, tmp_path, monkeypatch):
        """Pasted text (non-URL) never trips the dedup short-circuit even when
        identical to a previous note; ``reused`` always returns False."""
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)

        for _ in range(2):
            r = client.post(
                "/api/clip",
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "Content-Type": "application/json",
                },
                json={"source": "a plain text note", "process": False},
            )
            assert r.status_code == 200
            assert r.json()["reused"] is False


class TestReadDedupRedirect:
    """services/read.read_url dedup after fetch rewrites the URL.

    Some sites redirect ``/post`` → ``/post/``; ``/x`` → canonical ``/x?id=42``.
    If we only dedup pre-fetch, the same canonical article gets re-LLMed.
    """

    def test_redirect_to_canonical_hits_dedup(self, tmp_path, monkeypatch):
        from neocortex.models import AppConfig, Profile
        from neocortex.reader.fetcher import Document
        from neocortex.services.read import read_url

        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)

        # Seed an existing note under the *canonical* URL.
        seeded = tmp_path / "topic" / "seed.md"
        seeded.parent.mkdir()
        seeded.write_text(
            '---\ntitle: "Seed"\nsource: "https://canonical.example/a/"\n---\n\nbody',
            encoding="utf-8",
        )

        class RedirectFetcher:
            def __init__(self, *_, **__): pass
            async def fetch(self, source):
                # Original input was the shortlink — fetcher rewrites to canonical.
                assert source == "https://short.example/a"
                return Document(
                    title="Canonical Title",
                    source="https://canonical.example/a/",
                    content="real body",
                )

        class FakeProvider:
            def max_context_tokens(self): return 100_000

        monkeypatch.setattr("neocortex.reader.fetcher.ContentFetcher", RedirectFetcher)
        monkeypatch.setattr("neocortex.llm.create_provider", lambda _cfg: FakeProvider())

        import asyncio
        result = asyncio.run(read_url(
            "https://short.example/a",
            notes_dir=tmp_path,
            cfg=AppConfig(provider="openai", api_key="sk-test"),
            profile=Profile(),
            lang=AppConfig().output_settings.language,
        ))

        assert result.reused is True
        assert result.saved_path == str(seeded)
        # No new file under topic/ (only the seed).
        topic_files = list((tmp_path / "topic").glob("*.md"))
        assert topic_files == [seeded]


class TestReadWebSocketDisconnect:
    """If the client drops mid-stream, the server must not crash; the
    on_progress callback simply stops landing and read_url runs to completion."""

    def test_client_disconnect_mid_stream(self, client, tmp_path, monkeypatch):
        from neocortex.models import AppConfig, Outline, OutlineItem, Profile
        from neocortex.reader.fetcher import Document

        cfg = AppConfig(provider="openai", api_key="sk-test")
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.load_config", lambda: cfg)
        monkeypatch.setattr("neocortex.config.load_profile", lambda: Profile())

        class StubFetcher:
            def __init__(self, *_, **__): pass
            async def fetch(self, source):
                return Document(title="Stub", source=source, content="body")

        async def stub_outline(*_, **__):
            return Outline(source="stub", items=[
                OutlineItem(title="X", marker="deep", reason="r"),
            ])

        async def stub_notes(*_args, on_chunk=None, **_kwargs):
            # Simulate two chunks — server tries to send progress on both,
            # but the client closes after we drain the first message.
            if on_chunk:
                await on_chunk(1, 2)
                await on_chunk(2, 2)
            return "# Stub\n\nbody"

        monkeypatch.setattr("neocortex.reader.fetcher.ContentFetcher", StubFetcher)
        monkeypatch.setattr("neocortex.reader.teacher.generate_outline", stub_outline)
        monkeypatch.setattr("neocortex.reader.teacher.generate_notes", stub_notes)

        class FakeProvider:
            def max_context_tokens(self): return 100_000
        monkeypatch.setattr("neocortex.llm.create_provider", lambda _cfg: FakeProvider())

        # Drain only the first event, then close the connection abruptly.
        with client.websocket_connect(
            "/api/read/ws",
            headers={"Authorization": f"Bearer {TOKEN}", "Host": EXPECTED_HOST},
        ) as ws:
            ws.send_json({"source": "https://example.com/x"})
            first = ws.receive_json()
            assert first["type"] == "progress"
            # Exiting the `with` triggers a client-side close.
        # Server-side: read_url should have completed and saved the note,
        # even though the WS send_json on subsequent progress events errored.
        # We can verify by checking the file was written.
        saved = list(tmp_path.rglob("*.md"))
        # At least one .md exists under the (auto-created) topic dir.
        assert any(p.name.endswith(".md") for p in saved), (
            f"expected the note to still be saved despite client disconnect; "
            f"got files: {saved}"
        )


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


class TestSearchEndpoint:
    """GET /api/search — FTS5 search."""

    def test_search_no_auth(self, client):
        r = client.get("/api/search", params={"q": "test"})
        assert r.status_code == 401

    def test_search_empty_query_400(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        r = client.get(
            "/api/search",
            params={"q": "  "},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert r.status_code == 400

    def test_search_no_index_returns_empty(self, client, tmp_path, monkeypatch):
        """Empty vault (no SQLite file yet) → 200 with hits=[] rather than 500."""
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        r = client.get(
            "/api/search",
            params={"q": "anything"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["hits"] == []
        assert body["query"] == "anything"
        assert body["mode"] == "fts"

    def test_search_finds_indexed_note(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        from neocortex.search import NoteIndex
        idx = NoteIndex(tmp_path / "neocortex.sqlite")
        idx.index_note("hello.md", "Hello World", "this fragment mentions asyncio gather concurrency")

        r = client.get(
            "/api/search",
            params={"q": "asyncio"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["hits"]) == 1
        assert body["hits"][0]["filename"] == "hello.md"
        assert "asyncio" in body["hits"][0]["snippet"].lower()


class TestAskEndpoint:
    """POST /api/ask — single-turn Q&A with auto-evaluate + insight save."""

    def test_ask_no_auth(self, client):
        r = client.post(
            "/api/ask",
            headers={"Content-Type": "application/json"},
            json={"question": "what is async/await?"},
        )
        assert r.status_code == 401

    def test_ask_missing_question(self, client):
        r = client.post(
            "/api/ask",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json={},
        )
        assert r.status_code == 422

    def test_ask_no_provider_returns_aborted(self, client, tmp_path, monkeypatch):
        """No api_key/provider configured → 200 + aborted=true (not 500)."""
        from neocortex.models import AppConfig

        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)
        monkeypatch.setattr(
            "neocortex.config.load_config", lambda: AppConfig()
        )

        r = client.post(
            "/api/ask",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json={"question": "explain map vs flatMap"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["aborted"] is True
        assert "provider" in (body["abort_reason"] or "").lower()
        assert body["answer"] == ""
        assert body["saved_as_insight"] is None

    def test_ask_happy_path_with_mock_provider(self, client, tmp_path, monkeypatch):
        """Mocked LLM returns canned answer; evaluator says no-save → no insight file."""
        from neocortex.models import AppConfig, Profile

        cfg = AppConfig(provider="openai", api_key="sk-test")

        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.load_config", lambda: cfg)
        monkeypatch.setattr("neocortex.config.load_profile", lambda: Profile())

        class FakeProvider:
            async def chat(self, messages):
                # Evaluator prompt has the literal "yes' or 'no" — return 'no' so
                # we exercise the non-save path here.
                last = messages[-1]["content"]
                if "'yes' or 'no'" in last:
                    return "no"
                return "**简短答案** — async 等待异步结果。"
            def max_context_tokens(self): return 100_000

        monkeypatch.setattr(
            "neocortex.llm.create_provider", lambda _cfg: FakeProvider()
        )

        r = client.post(
            "/api/ask",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json={"question": "什么是 async/await?"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["aborted"] is False
        assert body["answer"].startswith("**简短答案**")
        assert body["saved_as_insight"] is None  # evaluator returned 'no'
        assert body["elapsed_seconds"] >= 0

    def test_ask_saves_insight_when_evaluator_says_yes(
        self, client, tmp_path, monkeypatch
    ):
        from neocortex.models import AppConfig, Profile

        cfg = AppConfig(provider="openai", api_key="sk-test")

        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.load_config", lambda: cfg)
        monkeypatch.setattr("neocortex.config.load_profile", lambda: Profile())

        class YesProvider:
            async def chat(self, messages):
                last = messages[-1]["content"]
                if "'yes' or 'no'" in last:
                    return "yes"
                return "RNN 维护隐藏状态，Transformer 全并行 — 这种对比连接了…"
            def max_context_tokens(self): return 100_000

        monkeypatch.setattr(
            "neocortex.llm.create_provider", lambda _cfg: YesProvider()
        )

        r = client.post(
            "/api/ask",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json={"question": "Transformer 比 RNN 强在哪？"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["aborted"] is False
        assert body["saved_as_insight"] is not None
        assert body["saved_as_insight"].startswith("insights/")
        assert (tmp_path / body["saved_as_insight"]).exists()


class TestMapEndpoint:
    """GET /api/map — concept map Mermaid source."""

    def test_map_no_auth(self, client):
        r = client.get("/api/map")
        assert r.status_code == 401

    def test_empty_concepts_returns_placeholder(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)

        r = client.get(
            "/api/map",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["concepts_returned"] == 0
        assert "graph LR" in body["mermaid_source"]
        assert "kb compile" in body["mermaid_source"]

    def test_with_concepts_returns_graph(self, client, tmp_path, monkeypatch):
        """Two related concept files → graph with both nodes + an edge."""
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)

        concepts = tmp_path / "concepts"
        concepts.mkdir()
        (concepts / "transformer.md").write_text(
            "---\n"
            "name: Transformer\n"
            "evidence_count: 3\n"
            'related_concepts: ["Attention"]\n'
            "---\n# Transformer\n",
            encoding="utf-8",
        )
        (concepts / "attention.md").write_text(
            "---\n"
            "name: Attention\n"
            "evidence_count: 2\n"
            'related_concepts: ["Transformer"]\n'
            "---\n# Attention\n",
            encoding="utf-8",
        )

        r = client.get(
            "/api/map",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["concepts_returned"] == 2
        assert body["edges_returned"] == 1  # de-duped by sorted tuple
        src = body["mermaid_source"]
        assert "Transformer" in src
        assert "Attention" in src
        # mermaid has an edge declaration
        assert "-->" in src


class TestDailyEndpoint:
    """GET /api/daily — read-only daily briefing."""

    def test_daily_no_auth(self, client):
        r = client.get("/api/daily")
        assert r.status_code == 401

    def test_empty_vault_returns_empty_briefing(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)

        r = client.get(
            "/api/daily",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["surfacing"] == []
        assert body["due_flashcard_count"] == 0
        assert body["cluster_suggestions"] == []
        assert body["uncompiled_count"] == 0
        # Health pulse fields are all None / empty for an empty vault
        assert body["health_pulse"]["lint_score"] is None
        assert body["health_pulse"]["verify_score"] is None
        # Date present
        assert len(body["date"]) == 10  # YYYY-MM-DD

    def test_uncompiled_count_reads_real_compile_cache_shape(
        self, client, tmp_path, monkeypatch,
    ):
        from neocortex.compiler import CompileCache

        notes_dir = tmp_path / "vault"
        note = notes_dir / "clips" / "compiled.md"
        note.parent.mkdir(parents=True)
        note.write_text("already compiled", encoding="utf-8")
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: notes_dir)

        cache = CompileCache(tmp_path / "compile_cache.json", notes_root=notes_dir)
        cache.update(note)
        cache.save()

        r = client.get(
            "/api/daily",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["uncompiled_count"] == 0

    def test_surfacing_clip_appears(self, client, tmp_path, monkeypatch):
        """Clip with next_surface ≤ today and status=inbox → in surfacing."""
        from datetime import date, timedelta
        from neocortex.config import save_clip
        from neocortex.models import Clip

        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)

        old = (date.today() - timedelta(days=7)).isoformat()
        clip = Clip(
            id="abcd1234",
            source="https://example.com/x",
            content="body",
            title="Test Clip",
            status="inbox",
            summary="A short summary",
            related_concepts=["redis"],
            created_at=old,
            next_surface=date.today().isoformat(),
            surface_count=1,
        )
        save_clip(tmp_path, clip)

        r = client.get(
            "/api/daily",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["surfacing"]) == 1
        item = body["surfacing"][0]
        assert item["title"] == "Test Clip"
        assert item["summary"] == "A short summary"
        assert item["days_ago"] == 7
        assert item["related_concepts"] == ["redis"]
        # LLM context update skipped by default → empty
        assert item["context_update"] == ""

    def test_cluster_suggestion_at_three_clips(self, client, tmp_path, monkeypatch):
        """≥3 inbox clips touching the same concept → cluster suggestion."""
        from datetime import date
        from neocortex.config import save_clip
        from neocortex.models import Clip

        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)

        for i in range(3):
            save_clip(tmp_path, Clip(
                id=f"id{i:04d}",
                source=f"https://x.com/{i}",
                content=f"body {i}",
                title=f"Clip {i}",
                status="inbox",
                related_concepts=["transformer"],
                created_at=date.today().isoformat(),
                next_surface="2099-01-01",  # not in surfacing
                surface_count=0,
            ))

        r = client.get(
            "/api/daily",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert r.status_code == 200
        body = r.json()
        clusters = body["cluster_suggestions"]
        assert len(clusters) == 1
        assert clusters[0]["concept"] == "transformer"
        assert clusters[0]["clip_count"] == 3


class TestSurfaceEndpoint:
    """POST /api/daily/surface — advance a clip's next_surface schedule."""

    def test_surface_no_auth(self, client):
        r = client.post(
            "/api/daily/surface",
            headers={"Content-Type": "application/json"},
            json={"clip_id": "abcd1234"},
        )
        assert r.status_code == 401

    def test_surface_clip_not_found_404(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)
        r = client.post(
            "/api/daily/surface",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json={"clip_id": "ghost"},
        )
        assert r.status_code == 404

    def test_surface_advances_schedule(self, client, tmp_path, monkeypatch):
        from datetime import date, timedelta
        from neocortex.config import load_clips, save_clip
        from neocortex.models import Clip

        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)

        save_clip(tmp_path, Clip(
            id="surface1",
            source="https://example.com/x",
            content="body",
            title="t",
            status="inbox",
            created_at=(date.today() - timedelta(days=7)).isoformat(),
            next_surface=date.today().isoformat(),
            surface_count=1,
        ))

        r = client.post(
            "/api/daily/surface",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json={"clip_id": "surface1"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["clip_id"] == "surface1"
        assert body["surface_count"] == 2
        # surface_count=2 → SURFACE_INTERVALS[2] = 14 days out
        expected = (date.today() + timedelta(days=14)).isoformat()
        assert body["next_surface"] == expected
        assert body["absorbed"] is False

        # File on disk reflects the update
        updated = next(c for c in load_clips(tmp_path) if c.id == "surface1")
        assert updated.next_surface == expected
        assert updated.surface_count == 2

    def test_surface_absorbed_jumps_180_days(self, client, tmp_path, monkeypatch):
        from datetime import date, timedelta
        from neocortex.config import save_clip
        from neocortex.models import Clip

        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)

        save_clip(tmp_path, Clip(
            id="abs1", source="x", content="", title="t",
            status="inbox",
            created_at=date.today().isoformat(),
            next_surface=date.today().isoformat(),
            surface_count=0,
        ))

        r = client.post(
            "/api/daily/surface",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json={"clip_id": "abs1", "absorbed": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["absorbed"] is True
        assert body["next_surface"] == (date.today() + timedelta(days=180)).isoformat()


class TestReadWebSocket:
    """WS /api/read/ws — streams progress events + final ReadResult."""

    def test_ws_bad_token_rejected(self, client):
        # No token at all → 1008 close before accept.
        with pytest.raises(Exception):
            with client.websocket_connect("/api/read/ws") as ws:
                ws.receive_json()  # should never arrive

    def test_ws_streams_progress_and_done(self, client, tmp_path, monkeypatch):
        """Mock fetcher + LLM so the pipeline runs end-to-end fast."""
        from neocortex.models import AppConfig, Outline, OutlineItem, Profile
        from neocortex.reader.fetcher import Document

        cfg = AppConfig(provider="openai", api_key="sk-test")
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.get_notes_dir", lambda: tmp_path)
        monkeypatch.setattr("neocortex.config.load_config", lambda: cfg)
        monkeypatch.setattr("neocortex.config.load_profile", lambda: Profile())

        class StubFetcher:
            def __init__(self, *_, **__): pass
            async def fetch(self, source):
                return Document(
                    title="Stub Article", source=source,
                    content="A short fake article body for chunking.",
                )

        async def stub_outline(*_args, **_kwargs):
            return Outline(source="stub", items=[
                OutlineItem(title="Stub Topic", marker="deep", reason="r"),
            ])

        async def stub_notes(*_args, on_chunk=None, **_kwargs):
            # Pretend 2 chunks so we get two progress events.
            if on_chunk:
                await on_chunk(1, 2)
                await on_chunk(2, 2)
            return "# Stub Article\n\nfake body content"

        monkeypatch.setattr(
            "neocortex.reader.fetcher.ContentFetcher", StubFetcher
        )
        monkeypatch.setattr(
            "neocortex.reader.teacher.generate_outline", stub_outline
        )
        monkeypatch.setattr(
            "neocortex.reader.teacher.generate_notes", stub_notes
        )

        class FakeProvider:
            def max_context_tokens(self): return 100_000
        monkeypatch.setattr(
            "neocortex.llm.create_provider", lambda _cfg: FakeProvider()
        )

        events: list[dict] = []
        with client.websocket_connect(
            "/api/read/ws",
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Host": EXPECTED_HOST,
            },
        ) as ws:
            ws.send_json({"source": "https://example.com/article"})
            # Drain until we see 'done' or hit a sensible cap.
            for _ in range(20):
                msg = ws.receive_json()
                events.append(msg)
                if msg.get("type") == "done":
                    break

        phases = [e["phase"] for e in events if e.get("type") == "progress"]
        assert "fetch" in phases
        assert "outline" in phases
        assert "chunk" in phases
        assert "save" in phases

        done = events[-1]
        assert done["type"] == "done"
        assert done["result"]["aborted"] is False
        assert done["result"]["title"] == "Stub Article"
        assert done["result"]["word_count"] >= 1
        # File actually written
        from pathlib import Path
        assert Path(done["result"]["saved_path"]).exists()


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

    def test_provision_wipes_stale_files_when_old_pid_dead(self, tmp_path, monkeypatch):
        """Stale pid file from a SIGKILL'd previous run gets cleaned before reprovision.

        Without this, callers reading port/token mid-provision could see a
        mix of old + new fields and end up with the wrong token.
        """
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: tmp_path)

        # Seed stale files pointing at a definitely-dead pid (we just spawned
        # it and waited, but using a clearly fake one is faster).
        (tmp_path / "server.pid").write_text("999999", encoding="utf-8")
        (tmp_path / "server.port").write_text("11111", encoding="utf-8")
        (tmp_path / "server-token").write_text("old-stale-token", encoding="utf-8")

        from neocortex.server.runtime import cleanup_runtime, provision_runtime

        try:
            secrets = provision_runtime(port=22222)
            # New values fully overwrote stale ones — no leftover token.
            assert (tmp_path / "server.port").read_text() == "22222"
            assert (tmp_path / "server-token").read_text() == secrets.token
            assert secrets.token != "old-stale-token"
        finally:
            cleanup_runtime()

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
