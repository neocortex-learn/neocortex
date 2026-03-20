from __future__ import annotations

import pytest

from neocortex.search import NoteIndex


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
