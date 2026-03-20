"""Text-to-speech conversion for Neocortex notes using edge-tts."""

from __future__ import annotations

import re


# ── Voice mapping ──

VOICES = {
    "zh": "zh-CN-XiaoxiaoNeural",
    "en": "en-US-AriaNeural",
}

# edge-tts has practical limits on text length per request.
# We split at ~3000 characters to stay safe.
MAX_CHUNK_CHARS = 3000


def prepare_text_for_speech(markdown: str) -> str:
    """Convert Markdown notes into plain text suitable for TTS reading.

    Strips code blocks, tables, images, HTML tags, and Markdown formatting
    while preserving readable prose content.
    """
    if not markdown:
        return ""

    text = markdown

    # 1. Remove fenced code blocks (```...```)
    text = re.sub(r"```[\s\S]*?```", "", text)

    # 2. Replace inline code (`...`) with its content
    text = re.sub(r"`([^`]*)`", r"\1", text)

    # 3. Remove images ![alt](url)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)

    # 4. Convert Markdown links [text](url) to just text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)

    # 5. Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # 6. Remove table rows (lines that start with |)
    lines = text.split("\n")
    filtered_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|"):
            continue
        # Also skip table separator lines like |---|---|
        if re.match(r"^\|?[\s\-:|]+\|", stripped):
            continue
        filtered_lines.append(line)
    text = "\n".join(filtered_lines)

    # 7. Convert headers: # Title -> Title。
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\1。", text, flags=re.MULTILINE)

    # 8. Convert list items: - item / * item / 1. item -> item。
    text = re.sub(r"^\s*[-*+]\s+(.+)$", r"\1。", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+(.+)$", r"\1。", text, flags=re.MULTILINE)

    # 9. Remove bold/italic markers
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)

    # 10. Remove horizontal rules (--- / *** / ___)
    text = re.sub(r"^[\s]*[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # 11. Remove blockquote markers
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)

    # 12. Collapse multiple blank lines into one
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 13. Strip leading/trailing whitespace
    text = text.strip()

    return text


def _split_text(text: str) -> list[str]:
    """Split text into chunks that fit within edge-tts limits.

    Splits on paragraph boundaries (double newlines) first, then on sentence
    boundaries if a paragraph is still too long.
    """
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current_chunk) + len(para) + 2 <= MAX_CHUNK_CHARS:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
        else:
            if current_chunk:
                chunks.append(current_chunk)
            if len(para) <= MAX_CHUNK_CHARS:
                current_chunk = para
            else:
                # Split long paragraph on sentence boundaries
                sentence_chunks = _split_long_paragraph(para)
                for sc in sentence_chunks[:-1]:
                    chunks.append(sc)
                current_chunk = sentence_chunks[-1] if sentence_chunks else ""

    if current_chunk:
        chunks.append(current_chunk)

    return chunks if chunks else [text]


def _split_long_paragraph(para: str) -> list[str]:
    """Split a single long paragraph into chunks by sentence boundaries."""
    # Split on Chinese/English sentence endings
    sentences = re.split(r"(?<=[。！？.!?])\s*", para)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= MAX_CHUNK_CHARS:
            if current:
                current += " " + sentence
            else:
                current = sentence
        else:
            if current:
                chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)

    return chunks if chunks else [para]


async def text_to_speech(text: str, output_path: str, language: str = "zh") -> None:
    """Convert text to speech and save as MP3.

    Uses edge-tts with natural-sounding neural voices.
    For Chinese: zh-CN-XiaoxiaoNeural
    For English: en-US-AriaNeural

    Long texts are automatically split into chunks and concatenated.
    """
    try:
        import edge_tts
    except ImportError:
        raise RuntimeError(
            "edge-tts is required for audio generation. "
            "Install it with: pip install edge-tts"
        )

    voice = VOICES.get(language, VOICES["en"])
    chunks = _split_text(text)

    if len(chunks) == 1:
        communicate = edge_tts.Communicate(chunks[0], voice)
        await communicate.save(output_path)
    else:
        # For multiple chunks, generate temp files and concatenate
        import tempfile
        from pathlib import Path

        temp_files: list[str] = []
        temp_dir = tempfile.mkdtemp(prefix="neocortex_tts_")

        try:
            for i, chunk in enumerate(chunks):
                temp_path = str(Path(temp_dir) / f"chunk_{i:04d}.mp3")
                communicate = edge_tts.Communicate(chunk, voice)
                await communicate.save(temp_path)
                temp_files.append(temp_path)

            _concatenate_mp3(temp_files, output_path)
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


def _concatenate_mp3(input_files: list[str], output_path: str) -> None:
    """Concatenate multiple MP3 files by simple binary concatenation.

    MP3 is a frame-based format, so binary concatenation works correctly
    for playback in all standard players.
    """
    with open(output_path, "wb") as out_f:
        for in_path in input_files:
            with open(in_path, "rb") as in_f:
                out_f.write(in_f.read())
