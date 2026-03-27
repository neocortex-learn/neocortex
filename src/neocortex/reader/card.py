"""Visual card generator — transform notes into shareable PNG cards."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

_CARD_TEMPLATE = """\
<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  width: 1080px;
  font-family: "PingFang SC", -apple-system, "Noto Sans SC", sans-serif;
  background: {bg};
  color: {fg};
  padding: 60px 64px;
  line-height: 1.8;
}}
.header {{
  margin-bottom: 40px;
  padding-bottom: 32px;
  border-bottom: 3px solid {accent};
}}
.header h1 {{
  font-size: 36px;
  font-weight: 700;
  color: {accent};
  margin-bottom: 12px;
  letter-spacing: -0.5px;
}}
.header .source {{
  font-size: 16px;
  color: {dim};
}}
.section {{
  margin-bottom: 32px;
}}
.section h2 {{
  font-size: 24px;
  font-weight: 600;
  color: {accent};
  margin-bottom: 16px;
  padding-left: 16px;
  border-left: 4px solid {accent};
}}
.section p {{
  font-size: 18px;
  margin-bottom: 12px;
  color: {fg};
}}
.section ul, .section ol {{
  margin: 12px 0 12px 24px;
  font-size: 18px;
}}
.section li {{
  margin-bottom: 8px;
}}
.highlight {{
  background: {highlight_bg};
  border-radius: 12px;
  padding: 24px 28px;
  margin: 20px 0;
  font-size: 18px;
}}
.highlight strong {{
  color: {accent};
}}
.stats {{
  display: flex;
  gap: 20px;
  margin: 24px 0;
  flex-wrap: wrap;
}}
.stat-card {{
  background: {highlight_bg};
  border-radius: 12px;
  padding: 20px 24px;
  flex: 1;
  min-width: 200px;
  text-align: center;
}}
.stat-card .number {{
  font-size: 32px;
  font-weight: 700;
  color: {accent};
}}
.stat-card .label {{
  font-size: 14px;
  color: {dim};
  margin-top: 4px;
}}
.footer {{
  margin-top: 40px;
  padding-top: 24px;
  border-top: 1px solid {border};
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  color: {dim};
}}
code {{
  background: {highlight_bg};
  padding: 2px 8px;
  border-radius: 4px;
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 16px;
}}
strong {{ color: {accent}; }}
em {{ color: {yellow}; font-style: normal; }}
blockquote {{
  border-left: 3px solid {accent};
  padding: 12px 20px;
  margin: 16px 0;
  background: {highlight_bg};
  border-radius: 0 12px 12px 0;
  font-size: 18px;
}}
</style>
</head>
<body>
{body}
</body>
</html>
"""

# Dark theme (default)
_DARK = {
    "bg": "#1a1b26",
    "fg": "#c0caf5",
    "accent": "#7aa2f7",
    "dim": "#565f89",
    "border": "#3b4261",
    "highlight_bg": "#24283b",
    "yellow": "#e0af68",
}

# Light theme
_LIGHT = {
    "bg": "#fafafa",
    "fg": "#1a1b26",
    "accent": "#2e7de9",
    "dim": "#8990a3",
    "border": "#e0e0e0",
    "highlight_bg": "#f0f0f0",
    "yellow": "#8b6c0f",
}


def _extract_key_points(md_content: str, max_points: int = 8) -> list[dict]:
    """Extract key sections from markdown for card display."""
    # Strip frontmatter
    content = md_content
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            content = content[end + 3:].strip()

    sections: list[dict] = []
    current_heading = ""
    current_body: list[str] = []

    for line in content.split("\n"):
        m = re.match(r"^(#{1,3})\s+(.+)$", line)
        if m:
            if current_heading and current_body:
                body = "\n".join(current_body).strip()
                if body and not body.startswith("```"):
                    sections.append({"heading": current_heading, "body": body})
            current_heading = m.group(2).strip()
            current_body = []
        elif line.startswith("```"):
            continue
        else:
            current_body.append(line)

    if current_heading and current_body:
        body = "\n".join(current_body).strip()
        if body:
            sections.append({"heading": current_heading, "body": body})

    return sections[:max_points]


def _body_to_html(sections: list[dict]) -> str:
    """Convert extracted sections to card HTML body."""
    parts: list[str] = []
    for sec in sections:
        body_html = ""
        for line in sec["body"].split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("- ") or line.startswith("* "):
                body_html += f"<li>{_inline_html(line[2:])}</li>\n"
            elif line.startswith("> "):
                body_html += f"<blockquote>{_inline_html(line[2:])}</blockquote>\n"
            else:
                body_html += f"<p>{_inline_html(line)}</p>\n"
        if "<li>" in body_html:
            body_html = f"<ul>{body_html}</ul>"
        parts.append(f'<div class="section"><h2>{_esc(sec["heading"])}</h2>{body_html}</div>')
    return "\n".join(parts)


def _inline_html(text: str) -> str:
    text = _esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generate_card_html(
    md_content: str,
    title: str,
    source: str,
    date: str = "",
    lang: str = "en",
    theme: str = "dark",
) -> str:
    """Generate a card-style HTML from note content."""
    colors = _DARK if theme == "dark" else _LIGHT
    sections = _extract_key_points(md_content)
    body_html = _body_to_html(sections)

    header = f'<div class="header"><h1>{_esc(title)}</h1><div class="source">{_esc(source)}</div></div>'
    footer = f'<div class="footer"><span>Neocortex</span><span>{_esc(date)}</span></div>'

    full_body = header + "\n" + body_html + "\n" + footer

    return _CARD_TEMPLATE.format(lang=lang, body=full_body, **colors)


async def render_card_to_png(html_path: Path, png_path: Path, width: int = 1080) -> bool:
    """Render HTML card to PNG using Playwright. Returns True on success."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return False

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": width, "height": 800})
            await page.goto(f"file://{html_path.resolve()}")
            await page.wait_for_timeout(500)
            # Get actual content height
            height = await page.evaluate("document.body.scrollHeight")
            await page.set_viewport_size({"width": width, "height": height})
            await page.screenshot(path=str(png_path), full_page=True)
            await browser.close()
        return True
    except Exception:
        return False
