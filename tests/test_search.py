from __future__ import annotations

import struct
from unittest.mock import MagicMock

import pytest

from neocortex.search import NoteIndex, _merge_results, _prepare_query


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "test.sqlite"


@pytest.fixture()
def note_index(db_path):
    return NoteIndex(db_path)


@pytest.fixture()
def notes_dir(tmp_path):
    d = tmp_path / "notes"
    d.mkdir()
    return d


class TestIndexNoteAndSearch:
    def test_index_note_and_search(self, note_index):
        note_index.index_note(
            "ddia-ch8.md",
            "DDIA - Transactions",
            "# DDIA - Transactions\n\nSnapshot isolation and MVCC prevent lost updates.",
        )
        results = note_index.search("isolation")
        assert len(results) == 1
        assert results[0]["filename"] == "ddia-ch8.md"
        assert results[0]["title"] == "DDIA - Transactions"

    def test_search_chinese_content(self, note_index):
        note_index.index_note(
            "redis-notes.md",
            "Redis 学习笔记",
            "# Redis 学习笔记\n\n事务隔离级别与 MVCC 机制的关系。",
        )
        results = note_index.search("事务")
        assert len(results) == 1
        assert results[0]["filename"] == "redis-notes.md"


class TestIndexAll:
    def test_index_all(self, db_path, notes_dir):
        (notes_dir / "note1.md").write_text(
            "# First Note\n\nContent about distributed systems.",
            encoding="utf-8",
        )
        (notes_dir / "note2.md").write_text(
            "# Second Note\n\nContent about transaction isolation.",
            encoding="utf-8",
        )
        (notes_dir / "note3.md").write_text(
            "# Third Note\n\nContent about Kafka streams.",
            encoding="utf-8",
        )

        idx = NoteIndex(db_path)
        count = idx.index_all(notes_dir)
        assert count == 3

    def test_index_all_extracts_title(self, db_path, notes_dir):
        (notes_dir / "my-note.md").write_text(
            "# Custom Title Here\n\nSome body text.",
            encoding="utf-8",
        )
        idx = NoteIndex(db_path)
        idx.index_all(notes_dir)
        results = idx.search("body")
        assert len(results) == 1
        assert results[0]["title"] == "Custom Title Here"

    def test_index_all_uses_stem_when_no_heading(self, db_path, notes_dir):
        (notes_dir / "no-heading.md").write_text(
            "Just plain text without any heading.",
            encoding="utf-8",
        )
        idx = NoteIndex(db_path)
        idx.index_all(notes_dir)
        results = idx.search("plain")
        assert len(results) == 1
        assert results[0]["title"] == "no-heading"

    def test_index_all_skips_non_md(self, db_path, notes_dir):
        (notes_dir / "note.md").write_text("# Note\n\nContent.", encoding="utf-8")
        (notes_dir / "data.json").write_text('{"key": "value"}', encoding="utf-8")
        idx = NoteIndex(db_path)
        count = idx.index_all(notes_dir)
        assert count == 1

    def test_index_all_replaces_previous(self, db_path, notes_dir):
        (notes_dir / "note.md").write_text("# Old\n\nOld content.", encoding="utf-8")
        idx = NoteIndex(db_path)
        idx.index_all(notes_dir)

        (notes_dir / "note.md").write_text("# New\n\nNew content.", encoding="utf-8")
        count = idx.index_all(notes_dir)
        assert count == 1
        assert idx.search("Old") == []
        results = idx.search("New")
        assert len(results) == 1


class TestSearchNoResults:
    def test_search_no_results(self, note_index):
        note_index.index_note("a.md", "A", "Alpha bravo charlie.")
        results = note_index.search("zzzznotexist")
        assert results == []


class TestSearchSnippet:
    def test_search_snippet(self, note_index):
        note_index.index_note(
            "long.md",
            "Long Note",
            "The quick brown fox jumps over the lazy dog. "
            "Snapshot isolation prevents lost updates in database transactions. "
            "The end.",
        )
        results = note_index.search("isolation")
        assert len(results) == 1
        snippet = results[0]["snippet"]
        assert ">>>" in snippet
        assert "<<<" in snippet
        assert "isolation" in snippet


class TestHasIndex:
    def test_has_index_empty(self, note_index):
        assert note_index.has_index() is False

    def test_has_index_with_data(self, note_index):
        note_index.index_note("x.md", "X", "Some content here.")
        assert note_index.has_index() is True


class TestIndexNoteUpdates:
    def test_index_note_updates_no_duplicates(self, note_index):
        note_index.index_note("dup.md", "V1", "First version of the note.")
        note_index.index_note("dup.md", "V2", "Second version completely different.")

        results_v1 = note_index.search("First version")
        assert results_v1 == []

        results_v2 = note_index.search("Second version")
        assert len(results_v2) == 1
        assert results_v2[0]["title"] == "V2"
        assert results_v2[0]["filename"] == "dup.md"

    def test_multiple_notes_independent(self, note_index):
        note_index.index_note("a.md", "Note A", "Alpha content about systems.")
        note_index.index_note("b.md", "Note B", "Beta content about databases.")

        results_a = note_index.search("Alpha")
        assert len(results_a) == 1
        assert results_a[0]["filename"] == "a.md"

        results_b = note_index.search("Beta")
        assert len(results_b) == 1
        assert results_b[0]["filename"] == "b.md"


# ── _prepare_query ──


class TestPrepareQuery:
    def test_english_no_change(self):
        assert _prepare_query("distributed systems") == "distributed systems"

    def test_cjk_gets_prefix_star(self):
        result = _prepare_query("事务隔离")
        assert result == "事务隔离*"

    def test_mixed_cjk_and_english(self):
        result = _prepare_query("Redis 事务")
        assert result == "Redis 事务*"

    def test_already_has_star(self):
        result = _prepare_query("事务*")
        assert result == "事务*"

    def test_empty_query(self):
        assert _prepare_query("") == ""


# ── _merge_results ──


class TestMergeResults:
    def test_fts_only(self):
        fts = [
            {"filename": "a.md", "title": "A", "snippet": "snip a"},
            {"filename": "b.md", "title": "B", "snippet": "snip b"},
        ]
        results = _merge_results(fts, [], limit=10)
        assert len(results) == 2
        assert results[0]["filename"] == "a.md"
        assert results[0]["fts_score"] == 1.0
        assert results[0]["vec_score"] == 0.0

    def test_vec_only(self):
        vec = [
            {"filename": "a.md", "score": 0.9},
            {"filename": "b.md", "score": 0.7},
        ]
        results = _merge_results([], vec, limit=10)
        assert len(results) == 2
        assert results[0]["filename"] == "a.md"

    def test_merged_overlap_boosts_score(self):
        fts = [{"filename": "a.md", "title": "A", "snippet": "s"}]
        vec = [{"filename": "a.md", "score": 0.8}]
        results = _merge_results(fts, vec, limit=10)
        assert len(results) == 1
        assert results[0]["fts_score"] == 1.0
        assert results[0]["vec_score"] == 0.8
        expected_score = 0.5 * 1.0 + 0.5 * 0.8
        assert abs(results[0]["score"] - expected_score) < 0.001

    def test_limit_respected(self):
        fts = [{"filename": f"f{i}.md", "title": f"F{i}", "snippet": ""} for i in range(10)]
        results = _merge_results(fts, [], limit=3)
        assert len(results) == 3

    def test_empty_inputs(self):
        assert _merge_results([], [], limit=10) == []


# ── has_embeddings ──


class TestHasEmbeddings:
    def test_no_embeddings(self, note_index):
        assert note_index.has_embeddings() is False

    def test_with_embeddings(self, note_index):
        dim = 384
        fake_vec = [0.1] * dim
        blob = struct.pack(f"{dim}f", *fake_vec)
        with note_index._connect() as conn:
            conn.execute(
                "INSERT INTO note_embeddings (filename, embedding) VALUES (?, ?)",
                ("test.md", blob),
            )
        assert note_index.has_embeddings() is True


# ── semantic_search ──


class TestSemanticSearch:
    def test_returns_empty_without_model(self, note_index):
        note_index._embed_model = None
        results = note_index.semantic_search("query")
        assert results == []

    def test_semantic_search_with_mock_model(self, note_index):
        dim = 4
        # Insert two embeddings manually
        vec_a = [0.5, 0.5, 0.0, 0.0]
        vec_b = [0.0, 0.0, 0.5, 0.5]
        with note_index._connect() as conn:
            conn.execute(
                "INSERT INTO note_embeddings (filename, embedding) VALUES (?, ?)",
                ("a.md", struct.pack(f"{dim}f", *vec_a)),
            )
            conn.execute(
                "INSERT INTO note_embeddings (filename, embedding) VALUES (?, ?)",
                ("b.md", struct.pack(f"{dim}f", *vec_b)),
            )

        # Mock the embedding model to return a query vector similar to a.md
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([[0.6, 0.6, 0.0, 0.0]])
        note_index._embed_model = mock_model

        results = note_index.semantic_search("query about A", limit=10)
        assert len(results) >= 1
        assert results[0]["filename"] == "a.md"
        assert results[0]["score"] > 0.3

    def test_semantic_search_filters_low_similarity(self, note_index):
        dim = 4
        vec = [0.5, 0.5, 0.0, 0.0]
        with note_index._connect() as conn:
            conn.execute(
                "INSERT INTO note_embeddings (filename, embedding) VALUES (?, ?)",
                ("a.md", struct.pack(f"{dim}f", *vec)),
            )

        # Query vector orthogonal to stored vector → similarity ~ 0
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([[0.0, 0.0, 0.6, 0.6]])
        note_index._embed_model = mock_model

        results = note_index.semantic_search("unrelated query")
        assert results == []


# ── hybrid_search ──


class TestHybridSearch:
    def test_hybrid_combines_fts_and_vec(self, note_index):
        note_index.index_note("a.md", "Alpha", "Alpha content about databases.")
        note_index.index_note("b.md", "Beta", "Beta content about systems.")

        dim = 4
        vec_a = [0.5, 0.5, 0.0, 0.0]
        vec_b = [0.0, 0.0, 0.5, 0.5]
        with note_index._connect() as conn:
            conn.execute("DELETE FROM note_embeddings")
            conn.execute(
                "INSERT INTO note_embeddings (filename, embedding) VALUES (?, ?)",
                ("a.md", struct.pack(f"{dim}f", *vec_a)),
            )
            conn.execute(
                "INSERT INTO note_embeddings (filename, embedding) VALUES (?, ?)",
                ("b.md", struct.pack(f"{dim}f", *vec_b)),
            )

        mock_model = MagicMock()
        mock_model.embed.return_value = iter([[0.6, 0.6, 0.0, 0.0]])
        note_index._embed_model = mock_model

        results = note_index.hybrid_search("Alpha")
        assert len(results) >= 1
        filenames = [r["filename"] for r in results]
        assert "a.md" in filenames


# ── index_all_with_progress ──


class TestIndexAllWithProgress:
    def test_callbacks_called(self, db_path, notes_dir):
        (notes_dir / "note1.md").write_text("# N1\nContent one.", encoding="utf-8")
        (notes_dir / "note2.md").write_text("# N2\nContent two.", encoding="utf-8")

        idx = NoteIndex(db_path)
        fts_counts = []
        embed_progress = []

        # Mock embedding model — return a fresh iterator each call
        mock_model = MagicMock()
        mock_model.embed.side_effect = lambda texts: iter([[0.1] * 4] * len(texts))
        idx._embed_model = mock_model

        count = idx.index_all_with_progress(
            notes_dir,
            on_fts_done=lambda c: fts_counts.append(c),
            on_embed_progress=lambda cur, tot: embed_progress.append((cur, tot)),
        )
        assert count == 2
        assert fts_counts == [2]
        assert len(embed_progress) == 2
        assert embed_progress[-1][1] == 2
