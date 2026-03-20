from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from neocortex.models import (
    Calibration,
    Language,
    LearningStyle,
    Outline,
    OutlineItem,
    Persona,
    Profile,
)
from neocortex.reader.chunker import (
    Chunk,
    _is_cjk_heavy,
    chunk_content,
    estimate_tokens,
)
from neocortex.reader.fetcher import ContentFetcher, Document, Section
from neocortex.reader.teacher import (
    _style_instruction,
    generate_outline,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(**kwargs) -> Profile:
    defaults = {
        "persona": Persona(language=Language.EN),
        "calibration": Calibration(),
    }
    defaults.update(kwargs)
    return Profile(**defaults)


def _make_provider_mock(response: str) -> AsyncMock:
    provider = AsyncMock()
    provider.chat = AsyncMock(return_value=response)
    provider.max_context_tokens = MagicMock(return_value=128_000)
    provider.name = MagicMock(return_value="mock")
    return provider


# ===========================================================================
# 1. ContentFetcher
# ===========================================================================


class TestContentFetcherMarkdown:
    @pytest.mark.asyncio
    async def test_markdown_sections(self, tmp_path: Path):
        md = tmp_path / "doc.md"
        md.write_text(
            "# Title\n\nIntro paragraph.\n\n## Section A\n\nContent A.\n\n## Section B\n\nContent B.\n",
            encoding="utf-8",
        )
        fetcher = ContentFetcher()
        doc = await fetcher.fetch(str(md))

        assert doc.title == "Title"
        assert doc.source == str(md)
        assert len(doc.sections) == 3
        assert doc.sections[0].title == "Title"
        assert doc.sections[1].title == "Section A"
        assert doc.sections[2].title == "Section B"

    @pytest.mark.asyncio
    async def test_markdown_no_heading_creates_single_section(self, tmp_path: Path):
        md = tmp_path / "plain.md"
        md.write_text("Just some text without headings.", encoding="utf-8")
        fetcher = ContentFetcher()
        doc = await fetcher.fetch(str(md))

        assert doc.title == "plain"
        assert len(doc.sections) == 1
        assert doc.sections[0].content == "Just some text without headings."


class TestContentFetcherText:
    @pytest.mark.asyncio
    async def test_plain_text_file(self, tmp_path: Path):
        txt = tmp_path / "notes.txt"
        txt.write_text("Line 1\nLine 2\nLine 3", encoding="utf-8")
        fetcher = ContentFetcher()
        doc = await fetcher.fetch(str(txt))

        assert doc.title == "notes"
        assert "Line 1" in doc.content
        assert len(doc.sections) == 1

    @pytest.mark.asyncio
    async def test_file_not_found_raises_value_error(self):
        fetcher = ContentFetcher()
        with pytest.raises(ValueError, match="File not found"):
            await fetcher.fetch("/nonexistent/path/file.txt")

    @pytest.mark.asyncio
    async def test_markdown_file_not_found_raises_value_error(self):
        fetcher = ContentFetcher()
        with pytest.raises(ValueError, match="File not found"):
            await fetcher.fetch("/nonexistent/path/file.md")


class TestContentFetcherNonUtf8:
    @pytest.mark.asyncio
    async def test_non_utf8_text_falls_back_to_replace(self, tmp_path: Path):
        txt = tmp_path / "binary.txt"
        txt.write_bytes(b"hello \xff\xfe world")
        fetcher = ContentFetcher()
        doc = await fetcher.fetch(str(txt))

        assert "\ufffd" in doc.content
        assert "hello" in doc.content
        assert "world" in doc.content

    @pytest.mark.asyncio
    async def test_non_utf8_markdown_falls_back_to_replace(self, tmp_path: Path):
        md = tmp_path / "broken.md"
        md.write_bytes(b"# Title\n\nContent with \xff bytes.")
        fetcher = ContentFetcher()
        doc = await fetcher.fetch(str(md))

        assert "\ufffd" in doc.content
        assert doc.title == "Title"


# ===========================================================================
# 2. Chunker
# ===========================================================================


class TestEstimateTokens:
    def test_english_text(self):
        text = "The quick brown fox jumps over the lazy dog"
        tokens = estimate_tokens(text)
        assert tokens > 0
        assert tokens == len(text) // 4

    def test_chinese_text(self):
        text = "这是一段中文测试文本用于验证"
        tokens = estimate_tokens(text)
        assert tokens > 0

    def test_chinese_estimates_more_than_english_for_similar_meaning(self):
        english = "This is a test"
        chinese = "这是一个测试文本内容"
        en_ratio = estimate_tokens(english) / len(english) if english else 0
        zh_ratio = estimate_tokens(chinese) / len(chinese) if chinese else 0
        assert zh_ratio > en_ratio

    def test_empty_string(self):
        assert estimate_tokens("") == 0


class TestIsCjkHeavy:
    def test_chinese_text_returns_true(self):
        assert _is_cjk_heavy("这是一段完全中文的内容") is True

    def test_english_text_returns_false(self):
        assert _is_cjk_heavy("This is pure English text") is False

    def test_empty_returns_false(self):
        assert _is_cjk_heavy("") is False

    def test_mixed_below_threshold_returns_false(self):
        assert _is_cjk_heavy("Hello 你 world, this is mostly English") is False


class TestChunkContentShortDoc:
    def test_short_doc_single_chunk(self):
        doc = Document(
            title="Short",
            content="Brief content.",
            source="test.md",
            sections=[Section(title="Short", content="Brief content.", level=1)],
        )
        chunks = chunk_content(doc, max_tokens=4000)
        assert len(chunks) == 1
        assert chunks[0].content == "Brief content."

    def test_short_doc_no_sections(self):
        doc = Document(
            title="Short",
            content="Brief content.",
            source="test.md",
            sections=[],
        )
        chunks = chunk_content(doc, max_tokens=4000)
        assert len(chunks) == 1
        assert chunks[0].title == "Short"


class TestChunkContentLongDoc:
    def test_multiple_sections_become_multiple_chunks(self):
        sections = [
            Section(title=f"Section {i}", content=f"Content for section {i}.", level=1)
            for i in range(5)
        ]
        doc = Document(
            title="Multi",
            content="all content",
            source="test.md",
            sections=sections,
        )
        chunks = chunk_content(doc, max_tokens=4000)
        assert len(chunks) == 5

    def test_large_section_is_split(self):
        large_text = " ".join(["word"] * 50_000)
        doc = Document(
            title="Big",
            content=large_text,
            source="test.md",
            sections=[Section(title="Huge Section", content=large_text, level=1)],
        )
        chunks = chunk_content(doc, max_tokens=500)
        assert len(chunks) > 1
        for chunk in chunks:
            assert "Huge Section" in chunk.title

    def test_chinese_large_paragraph_split_by_chars(self):
        large_chinese = "测" * 20_000
        doc = Document(
            title="中文长文",
            content=large_chinese,
            source="test.md",
            sections=[Section(title="中文节", content=large_chinese, level=1)],
        )
        chunks = chunk_content(doc, max_tokens=500)
        assert len(chunks) > 1

    def test_prev_summary_set_on_subsequent_chunks(self):
        sections = [
            Section(title="First", content="Content of the first section.", level=1),
            Section(title="Second", content="Content of the second section.", level=1),
            Section(title="Third", content="Content of the third section.", level=1),
        ]
        doc = Document(
            title="Doc",
            content="all",
            source="test.md",
            sections=sections,
        )
        chunks = chunk_content(doc, max_tokens=4000)
        assert chunks[0].prev_summary == ""
        assert chunks[1].prev_summary != ""
        assert "First" in chunks[1].prev_summary
        assert chunks[2].prev_summary != ""
        assert "Second" in chunks[2].prev_summary


# ===========================================================================
# 3. Teacher (mock LLM)
# ===========================================================================


class TestGenerateOutline:
    @pytest.mark.asyncio
    async def test_valid_json_response(self):
        response_data = {
            "items": [
                {"title": "Introduction", "marker": "skip", "reason": "Already knows"},
                {"title": "Advanced Topics", "marker": "deep", "reason": "Knowledge gap"},
            ]
        }
        provider = _make_provider_mock(json.dumps(response_data))
        profile = _make_profile()
        doc = Document(
            title="Test Doc",
            content="content",
            source="test.md",
            sections=[
                Section(title="Introduction", content="intro", level=1),
                Section(title="Advanced Topics", content="advanced", level=1),
            ],
        )

        outline = await generate_outline(doc, profile, provider)

        assert isinstance(outline, Outline)
        assert len(outline.items) == 2
        assert outline.items[0].title == "Introduction"
        assert outline.items[0].marker == "skip"
        assert outline.items[1].marker == "deep"
        assert outline.source == "test.md"

    @pytest.mark.asyncio
    async def test_markdown_wrapped_json(self):
        inner_json = json.dumps({
            "items": [
                {"title": "Topic A", "marker": "brief", "reason": "Some reason"},
            ]
        })
        response = f"```json\n{inner_json}\n```"
        provider = _make_provider_mock(response)
        profile = _make_profile()
        doc = Document(title="Doc", content="c", source="s.md", sections=[])

        outline = await generate_outline(doc, profile, provider)

        assert len(outline.items) == 1
        assert outline.items[0].title == "Topic A"
        assert outline.items[0].marker == "brief"

    @pytest.mark.asyncio
    async def test_invalid_json_raises_value_error(self):
        provider = _make_provider_mock("This is not JSON at all, no braces here")
        profile = _make_profile()
        doc = Document(title="Doc", content="c", source="s.md", sections=[])

        with pytest.raises(ValueError, match="Failed to parse outline"):
            await generate_outline(doc, profile, provider)

    @pytest.mark.asyncio
    async def test_invalid_marker_normalized_to_brief(self):
        response_data = {
            "items": [
                {"title": "X", "marker": "invalid_marker", "reason": "test"},
            ]
        }
        provider = _make_provider_mock(json.dumps(response_data))
        profile = _make_profile()
        doc = Document(title="Doc", content="c", source="s.md", sections=[])

        outline = await generate_outline(doc, profile, provider)
        assert outline.items[0].marker == "brief"


class TestStyleInstruction:
    def test_code_examples(self):
        profile = _make_profile(persona=Persona(learning_style=LearningStyle.CODE_EXAMPLES))
        result = _style_instruction(profile)
        assert "code examples" in result.lower()

    def test_theory_first(self):
        profile = _make_profile(persona=Persona(learning_style=LearningStyle.THEORY_FIRST))
        result = _style_instruction(profile)
        assert "theory" in result.lower()

    def test_just_do_it(self):
        profile = _make_profile(persona=Persona(learning_style=LearningStyle.JUST_DO_IT))
        result = _style_instruction(profile)
        assert "concise" in result.lower()

    def test_compare_with_known(self):
        profile = _make_profile(persona=Persona(learning_style=LearningStyle.COMPARE_WITH_KNOWN))
        result = _style_instruction(profile)
        assert "compare" in result.lower() or "analogies" in result.lower()

    def test_none_style_returns_empty(self):
        profile = _make_profile(persona=Persona(learning_style=None))
        result = _style_instruction(profile)
        assert result == ""
