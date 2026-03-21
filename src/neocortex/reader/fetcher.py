"""Content fetching — URL, PDF, EPUB, image, Markdown, and plain text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from markdownify import markdownify as md
from readability import Document as ReadabilityDoc

if TYPE_CHECKING:
    from neocortex.llm.base import LLMProvider

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}

_IMAGE_PROMPT = (
    "Please carefully examine this image and extract ALL content from it.\n"
    "If it contains text, transcribe the text verbatim.\n"
    "If it contains diagrams or architecture drawings, describe the structure, "
    "components, and relationships in detail.\n"
    "If it contains code, transcribe the code exactly.\n"
    "If it contains charts, tables, or data, describe the data thoroughly.\n"
    "If it contains screenshots of UI, describe the interface elements and their states.\n"
    "Be thorough, detailed, and preserve the original structure as much as possible."
)


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

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider

    async def fetch(self, source: str) -> Document:
        if source.startswith("http://") or source.startswith("https://"):
            return await self._fetch_url(source)
        suffix = Path(source).suffix.lower()
        if suffix == ".pdf":
            return await self._fetch_pdf(source)
        if suffix == ".epub":
            return self._read_epub(source)
        if suffix in _IMAGE_EXTENSIONS:
            return await self._fetch_image(source)
        if suffix == ".md":
            return self._read_markdown(source)
        return self._read_text(source)

    async def _fetch_url(self, url: str) -> Document:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            raw_html = resp.text

        readable = ReadabilityDoc(raw_html)
        title = readable.title()
        summary_html = readable.summary()

        markdown_text = self._html_to_markdown(summary_html)

        # Fallback to Jina Reader if readability extracted very little content
        # Skip for private/local URLs to avoid leaking sensitive URLs to third party
        if len(markdown_text.strip()) < 100 and self._is_public_url(url):
            jina_doc = await self._fetch_url_jina(url)
            if jina_doc is not None:
                return jina_doc

        sections = self._parse_html_sections(summary_html)

        return Document(
            title=title,
            content=markdown_text,
            source=url,
            sections=sections,
        )

    @staticmethod
    def _is_public_url(url: str) -> bool:
        """Check if URL is safe to send to third-party services."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or ""
        # Block private/local hosts
        if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            return False
        if host.endswith(".local") or host.endswith(".internal"):
            return False
        # Block private IP ranges
        if host.startswith(("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                           "172.20.", "172.21.", "172.22.", "172.23.",
                           "172.24.", "172.25.", "172.26.", "172.27.",
                           "172.28.", "172.29.", "172.30.", "172.31.",
                           "192.168.")):
            return False
        # Block URLs with sensitive query params
        query = parsed.query.lower()
        sensitive_params = ("token", "key", "secret", "password", "auth", "credential", "sig", "signature")
        if any(param in query for param in sensitive_params):
            return False
        return True

    async def _fetch_url_jina(self, url: str) -> Document | None:
        jina_url = f"https://r.jina.ai/{url}"
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                resp = await client.get(
                    jina_url,
                    headers={"Accept": "text/markdown"},
                )
                resp.raise_for_status()
                text = resp.text
        except (httpx.HTTPError, httpx.TimeoutException):
            return None

        if len(text.strip()) < 50:
            return None

        # Jina Reader may prepend metadata lines (Title:, URL Source:)
        content = text
        title = ""
        title_match = re.match(r"Title:\s*(.+)", text)
        if title_match:
            title = title_match.group(1).strip()
            lines = text.split("\n")
            content_start = 0
            for i, line in enumerate(lines):
                if line.startswith("Title:") or line.startswith("URL Source:") or line.startswith("Markdown Content:"):
                    content_start = i + 1
                elif line.strip() == "" and content_start > 0:
                    content_start = i + 1
                    break
            content = "\n".join(lines[content_start:]).strip()

        if not title:
            heading_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
            title = heading_match.group(1).strip() if heading_match else url

        sections = self._parse_markdown_sections(content)
        if not sections:
            sections = [Section(title=title, content=content, level=1)]

        return Document(
            title=title,
            content=content,
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

    async def _fetch_image(self, path: str) -> Document:
        if self._provider is None:
            raise ValueError("LLM provider required for image reading. Configure a provider first.")

        file_path = Path(path)
        if not file_path.exists():
            raise ValueError(f"File not found: {path}")

        # Guard against oversized images (max 20MB)
        file_size = file_path.stat().st_size
        max_size = 20 * 1024 * 1024  # 20MB
        if file_size > max_size:
            raise ValueError(f"Image too large ({file_size // 1024 // 1024}MB). Maximum is 20MB.")

        image_data = file_path.read_bytes()
        suffix = file_path.suffix.lower()
        media_type = _MEDIA_TYPES.get(suffix, "image/png")

        content = await self._provider.describe_image(image_data, media_type, _IMAGE_PROMPT)
        title = file_path.stem

        return Document(
            title=title,
            content=content,
            source=path,
            sections=[Section(title=title, content=content, level=1)],
        )

    def _read_epub(self, path: str) -> Document:
        from ebooklib import epub
        from ebooklib import ITEM_DOCUMENT

        file_path = Path(path)
        if not file_path.exists():
            raise ValueError(f"File not found: {path}")

        book = epub.read_epub(path)
        meta_title = book.get_metadata("DC", "title")
        title = meta_title[0][0] if meta_title else file_path.stem

        sections: list[Section] = []
        full_text_parts: list[str] = []

        for item in book.get_items_of_type(ITEM_DOCUMENT):
            item_content = item.get_content().decode("utf-8", errors="replace")
            plain_text = self._html_to_markdown(item_content)
            if not plain_text.strip():
                continue

            chapter_title = ""
            heading_match = re.search(
                r"<h[1-3][^>]*>(.*?)</h[1-3]>", item_content,
                re.IGNORECASE | re.DOTALL,
            )
            if heading_match:
                chapter_title = re.sub(r"<[^>]+>", "", heading_match.group(1)).strip()

            if not chapter_title:
                name = getattr(item, "file_name", "") or ""
                chapter_title = Path(name).stem if name else ""

            sections.append(Section(title=chapter_title, content=plain_text.strip(), level=1))
            full_text_parts.append(plain_text.strip())

        full_text = "\n\n".join(full_text_parts)

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
            plain = self._html_to_markdown(html)
            if plain.strip():
                return [Section(title="", content=plain.strip(), level=1)]
            return []

        sections: list[Section] = []

        preamble = html[: matches[0].start()]
        preamble_text = self._html_to_markdown(preamble).strip()
        if preamble_text:
            sections.append(Section(title="", content=preamble_text, level=1))

        for i, match in enumerate(matches):
            level = int(match.group(1)[1])
            heading_text = tag_re.sub("", match.group(2)).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
            body_html = html[start:end]
            body_text = self._html_to_markdown(body_html).strip()
            sections.append(Section(title=heading_text, content=body_text, level=level))

        return sections

    def _html_to_markdown(self, raw_html: str) -> str:
        text = md(raw_html, heading_style="ATX", strip=["img", "script", "style"])
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
