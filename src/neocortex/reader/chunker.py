"""Smart content chunking for LLM consumption."""

from __future__ import annotations

import re
from dataclasses import dataclass

from neocortex.reader.fetcher import Document, Section


@dataclass
class Chunk:
    title: str
    content: str
    position: str
    prev_summary: str = ""


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk_pattern = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
    cjk_count = len(cjk_pattern.findall(text))
    non_cjk_count = len(text) - cjk_count
    return cjk_count // 2 + non_cjk_count // 4


def _build_position(section: Section, parent_titles: list[str]) -> str:
    parts = [t for t in parent_titles if t]
    if section.title:
        parts.append(section.title)
    return " > ".join(parts) if parts else "Content"


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = re.split(r"\n\n+", text.strip())
    return [p.strip() for p in paragraphs if p.strip()]


def _is_cjk_heavy(text: str) -> bool:
    if not text:
        return False
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf')
    return cjk / len(text) > 0.3


def _chunk_long_text(
    text: str,
    max_tokens: int,
    title: str,
    position: str,
) -> list[Chunk]:
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return []

    chunks: list[Chunk] = []
    current_parts: list[str] = []
    current_tokens = 0
    part_index = 1

    for para in paragraphs:
        para_tokens = estimate_tokens(para)

        if para_tokens > max_tokens:
            if current_parts:
                chunks.append(Chunk(
                    title=f"{title} (part {part_index})" if title else f"Part {part_index}",
                    content="\n\n".join(current_parts),
                    position=position,
                ))
                part_index += 1
                current_parts = []
                current_tokens = 0

            if _is_cjk_heavy(para):
                chars_per_chunk = max(max_tokens * 2, 500)
                words = [para[i:i+chars_per_chunk] for i in range(0, len(para), chars_per_chunk)]
            else:
                words = para.split()
            buf: list[str] = []
            buf_tokens = 0
            for word in words:
                wt = estimate_tokens(word + " ")
                if buf_tokens + wt > max_tokens and buf:
                    chunks.append(Chunk(
                        title=f"{title} (part {part_index})" if title else f"Part {part_index}",
                        content=" ".join(buf),
                        position=position,
                    ))
                    part_index += 1
                    buf = []
                    buf_tokens = 0
                buf.append(word)
                buf_tokens += wt
            if buf:
                current_parts.append(" ".join(buf))
                current_tokens += buf_tokens
            continue

        if current_tokens + para_tokens > max_tokens and current_parts:
            chunks.append(Chunk(
                title=f"{title} (part {part_index})" if title else f"Part {part_index}",
                content="\n\n".join(current_parts),
                position=position,
            ))
            part_index += 1
            current_parts = []
            current_tokens = 0

        current_parts.append(para)
        current_tokens += para_tokens

    if current_parts:
        chunk_title = title
        if part_index > 1:
            chunk_title = f"{title} (part {part_index})" if title else f"Part {part_index}"
        chunks.append(Chunk(
            title=chunk_title,
            content="\n\n".join(current_parts),
            position=position,
        ))

    return chunks


def chunk_content(doc: Document, max_tokens: int = 4000) -> list[Chunk]:
    if not doc.sections:
        if estimate_tokens(doc.content) <= max_tokens:
            return [Chunk(
                title=doc.title,
                content=doc.content,
                position=doc.title,
            )]
        return _chunk_long_text(doc.content, max_tokens, doc.title, doc.title)

    parent_stack: list[str] = []
    level_stack: list[int] = []
    chunks: list[Chunk] = []

    for section in doc.sections:
        while level_stack and level_stack[-1] >= section.level:
            level_stack.pop()
            if parent_stack:
                parent_stack.pop()

        position = _build_position(section, parent_stack)
        section_tokens = estimate_tokens(section.content)

        if section_tokens <= max_tokens:
            chunks.append(Chunk(
                title=section.title or doc.title,
                content=section.content,
                position=position,
            ))
        else:
            sub_chunks = _chunk_long_text(
                section.content,
                max_tokens,
                section.title or doc.title,
                position,
            )
            chunks.extend(sub_chunks)

        if section.title:
            parent_stack.append(section.title)
            level_stack.append(section.level)

    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        prev_content = prev.content
        if len(prev_content) > 300:
            prev_content = prev_content[:300] + "..."
        chunks[i].prev_summary = f"[Previous: {prev.title}] {prev_content}"

    return chunks
