from __future__ import annotations

import math
import struct
from unittest.mock import MagicMock, patch

import pytest

from neocortex.search import NoteIndex, _cosine_similarity, _merge_results


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "test.sqlite"


@pytest.fixture()
def note_index(db_path):
    return NoteIndex(db_path)


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert math.isclose(_cosine_similarity(v, v), 1.0, rel_tol=1e-6)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert math.isclose(_cosine_similarity(a, b), 0.0, abs_tol=1e-9)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert math.isclose(_cosine_similarity(a, b), -1.0, rel_tol=1e-6)

    def test_zero_vector(self):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_both_zero_vectors(self):
        a = [0.0, 0.0]
        b = [0.0, 0.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_known_value(self):
        a = [1.0, 2.0, 3.0]
        b = [4.0, 5.0, 6.0]
        dot = 1 * 4 + 2 * 5 + 3 * 6  # 32
        norm_a = math.sqrt(1 + 4 + 9)  # sqrt(14)
        norm_b = math.sqrt(16 + 25 + 36)  # sqrt(77)
        expected = dot / (norm_a * norm_b)
        assert math.isclose(_cosine_similarity(a, b), expected, rel_tol=1e-6)


class TestMergeResults:
    def test_fts_only(self):
        fts = [
            {"filename": "a.md", "title": "A", "snippet": "snip A"},
            {"filename": "b.md", "title": "B", "snippet": "snip B"},
        ]
        vec = []
        results = _merge_results(fts, vec, limit=10)
        assert len(results) == 2
        assert results[0]["filename"] == "a.md"
        assert results[0]["fts_score"] == 1.0
        assert results[0]["vec_score"] == 0.0
        assert results[0]["score"] == 0.5 * 1.0 + 0.5 * 0.0

    def test_vec_only(self):
        fts = []
        vec = [
            {"filename": "x.md", "score": 0.9},
            {"filename": "y.md", "score": 0.7},
        ]
        results = _merge_results(fts, vec, limit=10)
        assert len(results) == 2
        assert results[0]["filename"] == "x.md"
        assert results[0]["fts_score"] == 0.0
        assert results[0]["vec_score"] == 0.9
        assert math.isclose(results[0]["score"], 0.5 * 0.9, rel_tol=1e-6)

    def test_merge_results_dedup(self):
        fts = [
            {"filename": "shared.md", "title": "Shared", "snippet": "snip"},
            {"filename": "fts-only.md", "title": "FTS", "snippet": "snip2"},
        ]
        vec = [
            {"filename": "shared.md", "score": 0.85},
            {"filename": "vec-only.md", "score": 0.6},
        ]
        results = _merge_results(fts, vec, limit=10)
        filenames = [r["filename"] for r in results]
        assert filenames.count("shared.md") == 1

        shared = next(r for r in results if r["filename"] == "shared.md")
        assert shared["fts_score"] == 1.0
        assert shared["vec_score"] == 0.85
        expected_score = 0.5 * 1.0 + 0.5 * 0.85
        assert math.isclose(shared["score"], expected_score, rel_tol=1e-6)

    def test_limit_respected(self):
        fts = [{"filename": f"f{i}.md", "title": f"F{i}", "snippet": ""} for i in range(10)]
        vec = [{"filename": f"v{i}.md", "score": 0.5} for i in range(10)]
        results = _merge_results(fts, vec, limit=5)
        assert len(results) == 5

    def test_empty_inputs(self):
        results = _merge_results([], [], limit=10)
        assert results == []


class TestSemanticSearchNoFastembed:
    def test_returns_empty_when_fastembed_missing(self, note_index):
        with patch.dict("sys.modules", {"fastembed": None}):
            if hasattr(note_index, "_embed_model"):
                del note_index._embed_model
            note_index._embed_model = None
            results = note_index.semantic_search("any query")
            assert results == []

    def test_hybrid_falls_back_to_fts(self, note_index):
        if hasattr(note_index, "_embed_model"):
            del note_index._embed_model
        note_index._embed_model = None

        with note_index._connect() as conn:
            conn.execute("DELETE FROM notes_fts WHERE filename = ?", ("test.md",))
            conn.execute(
                "INSERT INTO notes_fts (filename, title, content) VALUES (?, ?, ?)",
                ("test.md", "Test", "isolation levels in databases"),
            )

        results = note_index.hybrid_search("isolation")
        assert len(results) >= 1
        assert results[0]["filename"] == "test.md"


class TestIndexNoteEmbeddingRoundtrip:
    def test_roundtrip_with_mock_model(self, note_index):
        fake_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

        mock_model = MagicMock()
        mock_model.embed.return_value = iter([fake_embedding])
        note_index._embed_model = mock_model

        note_index.index_note_embedding("test.md", "Some content about databases")

        with note_index._connect() as conn:
            row = conn.execute(
                "SELECT embedding FROM note_embeddings WHERE filename = ?",
                ("test.md",),
            ).fetchone()

        assert row is not None
        blob = row[0]
        dim = len(blob) // 4
        stored = list(struct.unpack(f"{dim}f", blob))
        assert len(stored) == 5
        for a, b in zip(stored, fake_embedding):
            assert math.isclose(a, b, rel_tol=1e-5)

    def test_search_finds_indexed_note(self, note_index):
        embedding_a = [1.0, 0.0, 0.0]
        embedding_b = [0.0, 1.0, 0.0]
        query_embedding = [0.9, 0.1, 0.0]

        call_count = {"n": 0}

        def fake_embed(texts):
            call_count["n"] += 1
            if call_count["n"] <= 2:
                return iter([embedding_a if call_count["n"] == 1 else embedding_b])
            return iter([query_embedding])

        mock_model = MagicMock()
        mock_model.embed.side_effect = fake_embed
        note_index._embed_model = mock_model

        note_index.index_note_embedding("close.md", "Content close to query")
        note_index.index_note_embedding("far.md", "Content far from query")

        results = note_index.semantic_search("something close", limit=10)
        assert len(results) == 2
        assert results[0]["filename"] == "close.md"
        assert results[0]["score"] > results[1]["score"]


class TestHasEmbeddings:
    def test_no_embeddings(self, note_index):
        assert note_index.has_embeddings() is False

    def test_with_embeddings(self, note_index):
        blob = struct.pack("3f", 0.1, 0.2, 0.3)
        with note_index._connect() as conn:
            conn.execute(
                "INSERT INTO note_embeddings (filename, embedding) VALUES (?, ?)",
                ("x.md", blob),
            )
        assert note_index.has_embeddings() is True


class TestEnsureSchemaCreatesEmbeddingTable:
    def test_embedding_table_exists(self, note_index):
        with note_index._connect() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='note_embeddings'"
            ).fetchone()
        assert row is not None
        assert row[0] == "note_embeddings"
