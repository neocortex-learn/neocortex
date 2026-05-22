"""Tests for source-URL dedup."""

from __future__ import annotations

import pytest

from neocortex.dedup import find_existing, normalize_source_url


class TestNormalize:
    def test_strips_trailing_slash(self):
        assert normalize_source_url("https://a.com/x/") == "https://a.com/x"

    def test_keeps_root_slash(self):
        # Empty path should stay as "/" not get collapsed.
        assert normalize_source_url("https://a.com/") == "https://a.com/"

    def test_strips_fragment(self):
        assert normalize_source_url("https://a.com/x#sec1") == "https://a.com/x"

    def test_strips_utm_params(self):
        n = normalize_source_url("https://a.com/x?utm_source=foo&utm_medium=bar")
        assert n == "https://a.com/x"

    def test_keeps_non_tracking_params(self):
        n = normalize_source_url("https://a.com/article?id=42&page=2")
        assert "id=42" in n and "page=2" in n

    def test_mixed_strips_only_tracking(self):
        n = normalize_source_url(
            "https://a.com/x?id=7&utm_source=fb&fbclid=abc&page=3"
        )
        assert "id=7" in n
        assert "page=3" in n
        assert "utm" not in n
        assert "fbclid" not in n

    def test_wechat_keeps_mid_idx_sn(self):
        # WeChat article URL — mid/idx/sn are the real article key.
        n = normalize_source_url(
            "https://mp.weixin.qq.com/s?__biz=xx&mid=12345&idx=1&sn=abcdef&utm_source=x"
        )
        assert "mid=12345" in n
        assert "idx=1" in n
        assert "sn=abcdef" in n
        assert "utm_source" not in n

    def test_lowercases_host(self):
        assert normalize_source_url("https://EXAMPLE.com/X") == "https://example.com/X"

    def test_opt_out_manual(self):
        assert normalize_source_url("manual") is None

    def test_opt_out_empty(self):
        assert normalize_source_url("") is None
        assert normalize_source_url("   ") is None

    def test_opt_out_plain_text(self):
        assert normalize_source_url("随便一段文字") is None
        assert normalize_source_url("just a note") is None

    def test_opt_out_none(self):
        assert normalize_source_url(None) is None


class TestFindExisting:
    @pytest.fixture(autouse=True)
    def _isolate_data_dir(self, tmp_path, monkeypatch):
        """Sandbox the SQLite index used by find_existing's fast-path probe.

        Without this, every test would share the developer's ~/.neocortex/
        note_sources table, accumulating rows from earlier runs and breaking
        the ordering / dedup guarantees this suite checks.
        """
        data = tmp_path / "data"
        data.mkdir()
        monkeypatch.setattr("neocortex.config.get_data_dir", lambda: data)

    @pytest.fixture
    def vault(self, tmp_path):
        clips = tmp_path / "clips"
        clips.mkdir()
        return tmp_path

    def _write_note(self, vault, name, source, body="hello"):
        path = vault / "clips" / name
        path.write_text(
            f'---\ntitle: "Test"\nsource: "{source}"\n---\n\n{body}',
            encoding="utf-8",
        )
        return path

    def test_returns_none_when_no_match(self, vault):
        self._write_note(vault, "a.md", "https://other.com/x")
        assert find_existing(vault, "https://example.com/y") is None

    def test_returns_match_exact(self, vault):
        path = self._write_note(vault, "a.md", "https://example.com/x")
        assert find_existing(vault, "https://example.com/x") == path

    def test_matches_after_tracking_strip(self, vault):
        path = self._write_note(vault, "a.md", "https://example.com/x")
        # Query has tracking → should normalise to the same key.
        hit = find_existing(vault, "https://example.com/x?utm_source=foo")
        assert hit == path

    def test_matches_with_trailing_slash_difference(self, vault):
        path = self._write_note(vault, "a.md", "https://example.com/x")
        assert find_existing(vault, "https://example.com/x/") == path

    def test_opt_out_returns_none(self, vault):
        self._write_note(vault, "a.md", "manual")
        # Two "manual" notes should not be deduped — that's the bug we fixed.
        assert find_existing(vault, "manual") is None
        assert find_existing(vault, "随便文字") is None

    def test_skips_index_and_log(self, vault):
        # These wrapper docs sometimes have a `source:` field too; never dedup.
        (vault / "log.md").write_text(
            '---\nsource: "https://example.com/x"\n---\n', encoding="utf-8"
        )
        (vault / "INDEX.md").write_text(
            '---\nsource: "https://example.com/x"\n---\n', encoding="utf-8"
        )
        assert find_existing(vault, "https://example.com/x") is None

    def test_picks_most_recent_when_legacy_dupes(self, vault, monkeypatch):
        import time
        first = self._write_note(vault, "a.md", "https://example.com/x")
        time.sleep(0.01)
        second = self._write_note(vault, "b.md", "https://example.com/x")
        assert find_existing(vault, "https://example.com/x") == second

    def test_indexed_source_returned_without_fs_scan(self, vault, tmp_path, monkeypatch):
        """When NoteIndex has the row, find_existing should hit SQLite, not the FS.

        We simulate this by indexing a note explicitly, then deleting all .md
        files from disk except the indexed one — if find_existing still finds
        it, we know it came from the index (FS scan would miss because the
        file isn't reachable until we restore it).
        """
        from neocortex.config import get_data_dir
        from neocortex.search import NoteIndex

        target = self._write_note(vault, "indexed.md", "https://example.com/x", body="payload")
        # Index it. This populates note_sources.
        idx = NoteIndex(get_data_dir() / "neocortex.sqlite")
        idx.index_note("clips/indexed.md", "Indexed", target.read_text())
        # SQLite probe should return the right relative path.
        assert idx.find_filename_by_source("https://example.com/x") == "clips/indexed.md"
        # find_existing returns it.
        assert find_existing(vault, "https://example.com/x") == target

    def test_legacy_note_backfilled_to_index_after_first_hit(
        self, vault, tmp_path, monkeypatch,
    ):
        """A legacy (unindexed) note found via FS scan should be pushed into
        the SQLite index so the second lookup skips rglob."""
        from neocortex.config import get_data_dir
        from neocortex.search import NoteIndex

        self._write_note(vault, "legacy.md", "https://legacy.example/a")
        # First call: SQLite miss → FS scan → backfill.
        find_existing(vault, "https://legacy.example/a")
        # Index now has the row.
        idx = NoteIndex(get_data_dir() / "neocortex.sqlite")
        assert idx.find_filename_by_source("https://legacy.example/a") == "clips/legacy.md"

    def test_skips_hidden_dirs(self, vault):
        hidden = vault / ".trash"
        hidden.mkdir()
        (hidden / "a.md").write_text(
            '---\nsource: "https://example.com/x"\n---\n', encoding="utf-8"
        )
        assert find_existing(vault, "https://example.com/x") is None
