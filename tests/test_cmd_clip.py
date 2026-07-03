"""Tests for the pure-logic helpers extracted from cmd_clip.py's clip()/_run()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from neocortex.cmd_clip import (
    _detect_multi_images,
    _find_duplicate_clip,
    _gather_raw_input,
    _is_vision_unsupported_error,
    _resolve_effective_title,
    _resolve_llm_intent,
)


# ── _detect_multi_images ──


class TestDetectMultiImages:
    def test_single_source_returns_empty(self, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"\x89PNG")
        assert _detect_multi_images([str(img)]) == []

    def test_none_sources_returns_empty(self):
        assert _detect_multi_images(None) == []

    def test_multiple_images_detected(self, tmp_path):
        img1 = tmp_path / "a.png"
        img2 = tmp_path / "b.jpg"
        img1.write_bytes(b"\x89PNG")
        img2.write_bytes(b"\xff\xd8")
        result = _detect_multi_images([str(img1), str(img2)])
        assert len(result) == 2
        assert str(img1.expanduser()) in result
        assert str(img2.expanduser()) in result

    def test_non_image_files_ignored(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("x")
        f2.write_text("y")
        assert _detect_multi_images([str(f1), str(f2)]) == []

    def test_mixed_image_and_nonimage_only_images_kept(self, tmp_path):
        img = tmp_path / "a.png"
        txt = tmp_path / "b.txt"
        img.write_bytes(b"\x89PNG")
        txt.write_text("y")
        result = _detect_multi_images([str(img), str(txt)])
        assert result == [str(img.expanduser())]

    def test_nonexistent_paths_ignored(self):
        assert _detect_multi_images(["/no/such/a.png", "/no/such/b.png"]) == []


# ── _gather_raw_input ──


class TestGatherRawInput:
    def test_paste_false_uses_source(self):
        assert _gather_raw_input(["hello world"], "hello world", paste=False) == "hello world"

    def test_paste_true_falls_back_to_pbpaste_text(self):
        mock_result = MagicMock(stdout="pasted text\n")
        with patch("neocortex.cmd_clip._try_paste_image", return_value=""), \
             patch("subprocess.run", return_value=mock_result):
            result = _gather_raw_input(None, None, paste=True)
        assert result == "pasted text"

    def test_paste_true_prefers_clipboard_image(self):
        with patch("neocortex.cmd_clip._try_paste_image", return_value="/tmp/clip.png"):
            result = _gather_raw_input(None, None, paste=True)
        assert result == "/tmp/clip.png"

    def test_no_paste_no_source_returns_empty(self):
        assert _gather_raw_input(None, None, paste=False) == ""

    def test_pbpaste_failure_falls_back_to_empty(self):
        import subprocess
        with patch("neocortex.cmd_clip._try_paste_image", return_value=""), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pbpaste", timeout=5)):
            result = _gather_raw_input(None, None, paste=True)
        assert result == ""


# ── _find_duplicate_clip ──


class TestFindDuplicateClip:
    def test_force_always_returns_none(self, tmp_path):
        with patch("neocortex.dedup.find_existing", return_value=tmp_path / "x.md"):
            assert _find_duplicate_clip(tmp_path, "https://example.com/x", force=True) is None

    def test_non_url_returns_none(self, tmp_path):
        assert _find_duplicate_clip(tmp_path, "just a thought", force=False) is None

    def test_existing_url_returns_path(self, tmp_path):
        existing = tmp_path / "clips" / "x.md"
        with patch("neocortex.dedup.normalize_source_url", return_value="https://example.com/x"), \
             patch("neocortex.dedup.find_existing", return_value=existing):
            result = _find_duplicate_clip(tmp_path, "https://example.com/x", force=False)
        assert result == existing

    def test_no_existing_match_returns_none(self, tmp_path):
        with patch("neocortex.dedup.normalize_source_url", return_value="https://example.com/x"), \
             patch("neocortex.dedup.find_existing", return_value=None):
            assert _find_duplicate_clip(tmp_path, "https://example.com/x", force=False) is None


# ── _is_vision_unsupported_error ──


class TestIsVisionUnsupportedError:
    def test_image_url_token_matches(self):
        assert _is_vision_unsupported_error(Exception("invalid param: image_url not allowed"))

    def test_image_and_unsupported_matches(self):
        assert _is_vision_unsupported_error(Exception("Image input is UNSUPPORTED for this model"))

    def test_unrelated_error_does_not_match(self):
        assert not _is_vision_unsupported_error(Exception("rate limit exceeded"))

    def test_image_without_unsupported_does_not_match(self):
        assert not _is_vision_unsupported_error(Exception("image too large"))


# ── _resolve_llm_intent ──


class TestResolveLlmIntent:
    def test_explicit_opt_in(self):
        cfg = MagicMock(clip_default_process=False)
        wants, status = _resolve_llm_intent(True, cfg, weak_fetch=False)
        assert wants is True
        assert status == "skipped_user_opt_out"

    def test_explicit_opt_out(self):
        cfg = MagicMock(clip_default_process=True)
        wants, status = _resolve_llm_intent(False, cfg, weak_fetch=False)
        assert wants is False
        assert status == "skipped_user_opt_out"

    def test_default_from_config(self):
        cfg = MagicMock(clip_default_process=True)
        wants, status = _resolve_llm_intent(None, cfg, weak_fetch=False)
        assert wants is True

    def test_weak_fetch_forces_skip_even_when_wanted(self):
        cfg = MagicMock(clip_default_process=True)
        wants, status = _resolve_llm_intent(True, cfg, weak_fetch=True)
        assert wants is False
        assert status == "skipped_weak_fetch"

    def test_weak_fetch_no_effect_when_already_not_wanted(self):
        cfg = MagicMock(clip_default_process=False)
        wants, status = _resolve_llm_intent(False, cfg, weak_fetch=True)
        assert wants is False
        assert status == "skipped_user_opt_out"


# ── _resolve_effective_title ──


class TestResolveEffectiveTitle:
    def test_existing_title_kept(self):
        assert _resolve_effective_title("My Title", "content", {"summary": "s"}) == "My Title"

    def test_falls_back_to_summary(self):
        title = _resolve_effective_title("", "content", {"summary": "A short summary of the clip"})
        assert title == "A short summary of the clip"

    def test_summary_truncated_at_40_chars(self):
        long_summary = "x" * 60
        title = _resolve_effective_title("", "content", {"summary": long_summary})
        assert title == "x" * 40 + "…"

    def test_falls_back_to_content_first_line(self):
        title = _resolve_effective_title("", "first line here\nsecond line", {"summary": ""})
        assert title == "first line here"

    def test_all_empty_returns_empty_title(self):
        assert _resolve_effective_title("", "", {"summary": ""}) == ""
