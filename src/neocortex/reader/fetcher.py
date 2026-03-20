"""Content fetching — URL, PDF, Markdown, and plain text."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from readability import Document as ReadabilityDoc


@dataclass
class Section:
    title: str
    content: str
    level: int


@dataclass
class Document:
    title: str
    content: str
    source: str
    sections: list[Section] = field(default_factory=list)


class ContentFetcher:
    """Fetch and parse content from various sources."""

    async def fetch(self, source: str) -> Document:
        if source.startswith("http://") or source.startswith("https://"):
            return await self._fetch_url(source)
        if source.endswith(".pdf"):
            return await self._fetch_pdf(source)
        if source.endswith(".md"):
            return self._read_markdown(source)
        return self._read_text(source)

    async def _fetch_url(self, url: str) -> Document:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

        readable = ReadabilityDoc(html)
        title = readable.title()
        summary_html = readable.summary()

        sections = self._parse_html_sections(summary_html)
        plain_text = self._html_to_plain(summary_html)

        return Document(
            title=title,
            content=plain_text,
            source=url,
            sections=sections,
        )

    async def _fetch_pdf(self, path: str) -> Document:
        import fitz

        with fitz.open(path) as doc:
            title = doc.metadata.get("title", "") or Path(path).stem
            full_text_parts: list[str] = []
            sections: list[Section] = []

            for page in doc:
                page_text = page.get_text()
                full_text_parts.append(page_text)

            full_text = "\n".join(full_text_parts)

        raw_sections = self._split_by_headings(full_text)
        if raw_sections:
            sections = raw_sections
        else:
            sections = [Section(title=title, content=full_text, level=1)]

        return Document(
            title=title,
            content=full_text,
            source=path,
            sections=sections,
        )

    def _read_markdown(self, path: str) -> Document:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ValueError(f"File not found: {path}")
        except UnicodeDecodeError:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        title = Path(path).stem

        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        first_match = heading_pattern.search(text)
        if first_match:
            title = first_match.group(2).strip()

        sections = self._parse_markdown_sections(text)
        if not sections:
            sections = [Section(title=title, content=text, level=1)]

        return Document(
            title=title,
            content=text,
            source=path,
            sections=sections,
        )

    def _read_text(self, path: str) -> Document:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ValueError(f"File not found: {path}")
        except UnicodeDecodeError:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        title = Path(path).stem
        return Document(
            title=title,
            content=text,
            source=path,
            sections=[Section(title=title, content=text, level=1)],
        )

    def _parse_html_sections(self, html: str) -> list[Section]:
        heading_re = re.compile(
            r"<(h[1-6])[^>]*>(.*?)</\1>",
            re.IGNORECASE | re.DOTALL,
        )
        tag_re = re.compile(r"<[^>]+>")

        matches = list(heading_re.finditer(html))
        if not matches:
            plain = self._html_to_plain(html)
            if plain.strip():
                return [Section(title="", content=plain.strip(), level=1)]
            return []

        sections: list[Section] = []

        preamble = html[: matches[0].start()]
        preamble_text = self._html_to_plain(preamble).strip()
        if preamble_text:
            sections.append(Section(title="", content=preamble_text, level=1))

        for i, match in enumerate(matches):
            level = int(match.group(1)[1])
            heading_text = tag_re.sub("", match.group(2)).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
            body_html = html[start:end]
            body_text = self._html_to_plain(body_html).strip()
            sections.append(Section(title=heading_text, content=body_text, level=level))

        return sections

    def _html_to_plain(self, raw_html: str) -> str:
        text = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.IGNORECASE)
        text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _parse_markdown_sections(self, text: str) -> list[Section]:
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(heading_pattern.finditer(text))
        if not matches:
            return []

        sections: list[Section] = []

        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append(Section(title="", content=preamble, level=1))

        for i, match in enumerate(matches):
            level = len(match.group(1))
            heading_text = match.group(2).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            sections.append(Section(title=heading_text, content=body, level=level))

        return sections

    def _split_by_headings(self, text: str) -> list[Section]:
        heading_pattern = re.compile(
            r"^([A-Z][A-Z0-9 .:\-]{2,})$|^(Chapter|Section|Part)\s+\d+",
            re.MULTILINE,
        )
        matches = list(heading_pattern.finditer(text))
        if len(matches) < 2:
            return []

        sections: list[Section] = []
        for i, match in enumerate(matches):
            title = match.group(0).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                sections.append(Section(title=title, content=body, level=1))

        return sections
