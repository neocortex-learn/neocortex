"""Tests for the pure-logic helpers extracted from cmd_read.py's read()/_run_read_pipeline()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from neocortex.cmd_read import (
    _confirm_outline,
    _find_duplicate_read,
    _flashcard_source_note,
    _maybe_auto_open,
    _resolve_topic_dir,
    _write_read_note,
)
from neocortex.models import DomainSkill, Language, Outline, OutlineItem, Profile, Skills
from neocortex.reader.fetcher import Document


# ── _find_duplicate_read ──


class TestFindDuplicateRead:
    def test_force_always_returns_none(self, tmp_path):
        with patch("neocortex.dedup.find_existing", return_value=tmp_path / "x.md"):
            assert _find_duplicate_read(tmp_path, "https://example.com/x", force=True) is None

    def test_non_url_returns_none(self, tmp_path):
        assert _find_duplicate_read(tmp_path, "not a url", force=False) is None

    def test_existing_url_returns_path(self, tmp_path):
        existing = tmp_path / "note.md"
        with patch("neocortex.dedup.normalize_source_url", return_value="https://example.com/x"), \
             patch("neocortex.dedup.find_existing", return_value=existing):
            result = _find_duplicate_read(tmp_path, "https://example.com/x", force=False)
        assert result == existing

    def test_no_existing_match_returns_none(self, tmp_path):
        with patch("neocortex.dedup.normalize_source_url", return_value="https://example.com/x"), \
             patch("neocortex.dedup.find_existing", return_value=None):
            assert _find_duplicate_read(tmp_path, "https://example.com/x", force=False) is None


# ── _confirm_outline ──


class TestConfirmOutline:
    def test_default_yes(self):
        with patch("neocortex.cmd_read.Prompt.ask", return_value="y"):
            assert _confirm_outline(Language.EN) is True

    def test_explicit_no(self):
        with patch("neocortex.cmd_read.Prompt.ask", return_value="n"):
            assert _confirm_outline(Language.EN) is False

    def test_uppercase_no(self):
        with patch("neocortex.cmd_read.Prompt.ask", return_value="N"):
            assert _confirm_outline(Language.EN) is False


# ── _resolve_topic_dir ──


class TestResolveTopicDir:
    def _profile_with_domain(self, domain_name: str) -> Profile:
        return Profile(skills=Skills(domains={domain_name: DomainSkill()}))

    def test_falls_back_to_general_with_no_domains(self, tmp_path):
        doc = Document(title="Random Article", content="", source="https://x.com")
        outline = Outline(source="https://x.com", items=[])
        prof = Profile()
        result = _resolve_topic_dir(tmp_path, doc, outline, prof)
        assert result == tmp_path / "general"

    def test_matches_domain_from_title(self, tmp_path):
        doc = Document(title="Deep Dive into Backend Systems", content="", source="https://x.com")
        outline = Outline(source="https://x.com", items=[])
        prof = self._profile_with_domain("backend")
        result = _resolve_topic_dir(tmp_path, doc, outline, prof)
        assert result == tmp_path / "backend"

    def test_matches_domain_from_deep_outline_item(self, tmp_path):
        doc = Document(title="Unrelated Title", content="", source="https://x.com")
        outline = Outline(
            source="https://x.com",
            items=[OutlineItem(title="frontend rendering", marker="deep", reason="")],
        )
        prof = self._profile_with_domain("frontend")
        result = _resolve_topic_dir(tmp_path, doc, outline, prof)
        assert result == tmp_path / "frontend"

    def test_short_domain_words_not_matched(self, tmp_path):
        # domain words < 3 chars are skipped per the "len(dw) >= 3" guard
        doc = Document(title="ai is interesting", content="", source="https://x.com")
        outline = Outline(source="https://x.com", items=[])
        prof = self._profile_with_domain("ai")
        result = _resolve_topic_dir(tmp_path, doc, outline, prof)
        assert result == tmp_path / "general"


# ── _write_read_note ──


class TestWriteReadNote:
    def _outline(self, deep_titles=None):
        items = [OutlineItem(title=t, marker="deep", reason="") for t in (deep_titles or [])]
        return Outline(source="https://x.com", items=items)

    def test_writes_frontmatter_and_content(self, tmp_path):
        doc = Document(title="My Article!", content="", source="https://x.com")
        outline = self._outline()
        prof = Profile()

        note_path, full_content, safe_title = _write_read_note(
            tmp_path, doc, outline, prof, "# Notes\nBody.", "https://x.com", focus=None,
        )

        assert note_path.exists()
        assert safe_title == "my-article"
        assert 'title: "My Article!"' in full_content
        assert 'source: "https://x.com"' in full_content
        assert "# Notes\nBody." in full_content
        assert note_path.read_text(encoding="utf-8") == full_content

    def test_focus_added_to_frontmatter(self, tmp_path):
        doc = Document(title="Topic", content="", source="https://x.com")
        outline = self._outline()
        prof = Profile()

        _, full_content, _ = _write_read_note(
            tmp_path, doc, outline, prof, "body", "https://x.com", focus="async patterns",
        )
        assert 'focus: "async patterns"' in full_content

    def test_deep_topics_become_tags(self, tmp_path):
        doc = Document(title="Topic", content="", source="https://x.com")
        outline = self._outline(deep_titles=["Event Sourcing", "CQRS"])
        prof = Profile()

        _, full_content, _ = _write_read_note(
            tmp_path, doc, outline, prof, "body", "https://x.com", focus=None,
        )
        assert "tags:" in full_content
        assert "- event-sourcing" in full_content
        assert "- cqrs" in full_content

    def test_filename_collision_appends_counter(self, tmp_path):
        doc = Document(title="Same Title", content="", source="https://x.com")
        outline = self._outline()
        prof = Profile()

        note_path_1, _, _ = _write_read_note(tmp_path, doc, outline, prof, "body 1", "https://x.com", focus=None)
        note_path_2, _, _ = _write_read_note(tmp_path, doc, outline, prof, "body 2", "https://x.com", focus=None)

        assert note_path_1 != note_path_2
        assert note_path_1.exists()
        assert note_path_2.exists()
        assert "body 1" in note_path_1.read_text(encoding="utf-8")
        assert "body 2" in note_path_2.read_text(encoding="utf-8")

    def test_blank_title_falls_back_to_note(self, tmp_path):
        doc = Document(title="!!!", content="", source="https://x.com")
        outline = self._outline()
        prof = Profile()

        _, _, safe_title = _write_read_note(tmp_path, doc, outline, prof, "body", "https://x.com", focus=None)
        assert safe_title == "note"


# ── flashcard source path ──


class TestFlashcardSourceNote:
    def test_uses_vault_relative_path(self, tmp_path):
        note = tmp_path / "ai" / "same-name.md"
        note.parent.mkdir()
        note.write_text("x", encoding="utf-8")
        assert _flashcard_source_note(tmp_path, note) == "ai/same-name.md"

    def test_outside_vault_falls_back_to_basename(self, tmp_path):
        vault = tmp_path / "vault"
        outside = tmp_path / "outside.md"
        assert _flashcard_source_note(vault, outside) == "outside.md"


# ── _maybe_auto_open ──


class TestMaybeAutoOpen:
    def test_noop_when_auto_open_disabled(self, tmp_path):
        cfg = MagicMock()
        cfg.output_settings.auto_open = False
        with patch("subprocess.Popen") as mock_popen:
            _maybe_auto_open(tmp_path / "note.md", cfg)
        mock_popen.assert_not_called()

    def test_opens_file_when_enabled(self, tmp_path):
        cfg = MagicMock()
        cfg.output_settings.auto_open = True
        note_path = tmp_path / "note.md"
        with patch("platform.system", return_value="Darwin"), \
             patch("subprocess.Popen") as mock_popen:
            _maybe_auto_open(note_path, cfg)
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[0] == "open"
        assert args[1] == str(note_path)

    def test_swallows_oserror(self, tmp_path):
        cfg = MagicMock()
        cfg.output_settings.auto_open = True
        with patch("subprocess.Popen", side_effect=OSError("no such command")):
            _maybe_auto_open(tmp_path / "note.md", cfg)  # must not raise
