from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neocortex.tts import (
    MAX_CHUNK_CHARS,
    VOICES,
    _concatenate_mp3,
    _split_text,
    prepare_text_for_speech,
    text_to_speech,
)


# ---------------------------------------------------------------------------
# prepare_text_for_speech tests
# ---------------------------------------------------------------------------


class TestPrepareTextRemovesCodeBlocks:
    def test_fenced_code_block_removed(self):
        md = "Before code.\n\n```python\ndef hello():\n    pass\n```\n\nAfter code."
        result = prepare_text_for_speech(md)
        assert "def hello" not in result
        assert "```" not in result
        assert "Before code." in result
        assert "After code." in result

    def test_multiple_code_blocks(self):
        md = "A\n```\ncode1\n```\nB\n```js\ncode2\n```\nC"
        result = prepare_text_for_speech(md)
        assert "code1" not in result
        assert "code2" not in result
        assert "A" in result
        assert "B" in result
        assert "C" in result


class TestPrepareTextRemovesInlineCode:
    def test_inline_code_replaced_with_content(self):
        md = "Use `pip install` to install packages."
        result = prepare_text_for_speech(md)
        assert "`" not in result
        assert "pip install" in result

    def test_multiple_inline_codes(self):
        md = "Run `cmd1` and `cmd2`."
        result = prepare_text_for_speech(md)
        assert "cmd1" in result
        assert "cmd2" in result
        assert "`" not in result


class TestPrepareTextConvertsLinks:
    def test_link_text_preserved(self):
        md = "Visit [the docs](https://example.com) for more."
        result = prepare_text_for_speech(md)
        assert "the docs" in result
        assert "https://example.com" not in result
        assert "[" not in result
        assert "]" not in result

    def test_multiple_links(self):
        md = "[A](http://a.com) and [B](http://b.com)"
        result = prepare_text_for_speech(md)
        assert "A" in result
        assert "B" in result
        assert "http" not in result


class TestPrepareTextRemovesImages:
    def test_image_removed(self):
        md = "See below:\n\n![diagram](img.png)\n\nEnd."
        result = prepare_text_for_speech(md)
        assert "![" not in result
        assert "img.png" not in result
        assert "End." in result

    def test_image_with_alt_text(self):
        md = "![Architecture Overview](arch.svg)"
        result = prepare_text_for_speech(md)
        assert result.strip() == ""


class TestPrepareTextConvertsHeaders:
    def test_h1_to_text_with_period(self):
        md = "# Introduction"
        result = prepare_text_for_speech(md)
        assert "#" not in result
        assert "Introduction" in result

    def test_h3_to_text_with_period(self):
        md = "### Deep Dive"
        result = prepare_text_for_speech(md)
        assert "###" not in result
        assert "Deep Dive" in result


class TestPrepareTextRemovesTables:
    def test_table_rows_removed(self):
        md = (
            "Some text.\n\n"
            "| Name | Value |\n"
            "|------|-------|\n"
            "| A    | 1     |\n"
            "| B    | 2     |\n\n"
            "After table."
        )
        result = prepare_text_for_speech(md)
        assert "|" not in result
        assert "After table." in result

    def test_table_separator_removed(self):
        md = "| --- | --- |"
        result = prepare_text_for_speech(md)
        assert result.strip() == ""


class TestPrepareTextPreservesParagraphs:
    def test_plain_paragraphs(self):
        md = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = prepare_text_for_speech(md)
        assert "First paragraph." in result
        assert "Second paragraph." in result
        assert "Third paragraph." in result

    def test_chinese_text(self):
        md = "这是一段中文文本。\n\n这是另一段。"
        result = prepare_text_for_speech(md)
        assert "这是一段中文文本。" in result
        assert "这是另一段。" in result


class TestPrepareTextEmptyInput:
    def test_empty_string(self):
        assert prepare_text_for_speech("") == ""

    def test_whitespace_only(self):
        assert prepare_text_for_speech("   \n\n   ") == ""

    def test_only_code_block(self):
        md = "```python\nprint('hello')\n```"
        result = prepare_text_for_speech(md)
        assert result == ""


class TestPrepareTextBoldItalic:
    def test_bold_removed(self):
        md = "This is **bold** text."
        result = prepare_text_for_speech(md)
        assert "**" not in result
        assert "bold" in result

    def test_italic_removed(self):
        md = "This is *italic* text."
        result = prepare_text_for_speech(md)
        assert "*" not in result
        assert "italic" in result


class TestPrepareTextListItems:
    def test_unordered_list(self):
        md = "- Item one\n- Item two\n- Item three"
        result = prepare_text_for_speech(md)
        assert "-" not in result
        assert "Item one" in result
        assert "Item two" in result

    def test_ordered_list(self):
        md = "1. First\n2. Second\n3. Third"
        result = prepare_text_for_speech(md)
        assert "1." not in result
        assert "First" in result
        assert "Second" in result


class TestPrepareTextBlockquotes:
    def test_blockquote_marker_removed(self):
        md = "> This is a quote.\n> It continues here."
        result = prepare_text_for_speech(md)
        assert ">" not in result
        assert "This is a quote." in result


class TestPrepareTextHtml:
    def test_html_tags_removed(self):
        md = "Text with <br> and <div>content</div> here."
        result = prepare_text_for_speech(md)
        assert "<" not in result
        assert ">" not in result or result.count(">") == 0
        assert "content" in result


# ---------------------------------------------------------------------------
# _split_text tests
# ---------------------------------------------------------------------------


class TestSplitText:
    def test_short_text_single_chunk(self):
        text = "Short text."
        result = _split_text(text)
        assert result == ["Short text."]

    def test_long_text_split_on_paragraphs(self):
        para = "A" * 2000
        text = f"{para}\n\n{para}"
        result = _split_text(text)
        assert len(result) == 2
        assert result[0] == para
        assert result[1] == para

    def test_empty_text(self):
        result = _split_text("")
        assert result == [""]


# ---------------------------------------------------------------------------
# text_to_speech tests
# ---------------------------------------------------------------------------


def _make_mock_edge_tts():
    """Create a mock edge_tts module with a mock Communicate class."""
    mock_communicate_instance = MagicMock()
    mock_communicate_instance.save = AsyncMock()
    mock_module = MagicMock()
    mock_module.Communicate.return_value = mock_communicate_instance
    return mock_module, mock_communicate_instance


class TestTextToSpeech:
    @pytest.mark.asyncio
    async def test_single_chunk_calls_save(self):
        mock_module, mock_instance = _make_mock_edge_tts()

        with patch.dict("sys.modules", {"edge_tts": mock_module}):
            await text_to_speech("Hello world.", "/tmp/test.mp3", "en")

            mock_module.Communicate.assert_called_once_with(
                "Hello world.", VOICES["en"]
            )
            mock_instance.save.assert_awaited_once_with("/tmp/test.mp3")

    @pytest.mark.asyncio
    async def test_chinese_voice_selected(self):
        mock_module, mock_instance = _make_mock_edge_tts()

        with patch.dict("sys.modules", {"edge_tts": mock_module}):
            await text_to_speech("你好世界。", "/tmp/test.mp3", "zh")

            mock_module.Communicate.assert_called_once_with(
                "你好世界。", VOICES["zh"]
            )

    @pytest.mark.asyncio
    async def test_missing_edge_tts_raises_runtime_error(self):
        with patch.dict("sys.modules", {"edge_tts": None}):
            with pytest.raises(RuntimeError, match="edge-tts is required"):
                await text_to_speech("test", "/tmp/out.mp3", "en")

    @pytest.mark.asyncio
    async def test_unknown_language_falls_back_to_english(self):
        mock_module, mock_instance = _make_mock_edge_tts()

        with patch.dict("sys.modules", {"edge_tts": mock_module}):
            await text_to_speech("test", "/tmp/test.mp3", "fr")

            mock_module.Communicate.assert_called_once_with(
                "test", VOICES["en"]
            )


# ---------------------------------------------------------------------------
# _concatenate_mp3 tests
# ---------------------------------------------------------------------------


class TestConcatenateMp3:
    def test_concatenates_files(self, tmp_path):
        f1 = tmp_path / "a.mp3"
        f2 = tmp_path / "b.mp3"
        f1.write_bytes(b"AAA")
        f2.write_bytes(b"BBB")

        out = tmp_path / "out.mp3"
        _concatenate_mp3([str(f1), str(f2)], str(out))

        assert out.read_bytes() == b"AAABBB"

    def test_single_file(self, tmp_path):
        f1 = tmp_path / "a.mp3"
        f1.write_bytes(b"ONLY")

        out = tmp_path / "out.mp3"
        _concatenate_mp3([str(f1)], str(out))

        assert out.read_bytes() == b"ONLY"
