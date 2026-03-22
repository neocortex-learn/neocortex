"""Visual note renderer — generate HTML companion file with Mermaid rendering + interactive features."""

from __future__ import annotations

import re
from pathlib import Path

_MERMAID_BLOCK_RE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
  --bg: #1a1b26; --fg: #c0caf5; --accent: #7aa2f7;
  --bg2: #24283b; --border: #3b4261; --green: #9ece6a;
  --dim: #565f89; --red: #f7768e; --yellow: #e0af68;
}}
@media (prefers-color-scheme: light) {{
  :root {{
    --bg: #fff; --fg: #1a1b26; --accent: #2e7de9;
    --bg2: #f5f5f5; --border: #ddd; --green: #587539;
    --dim: #8990a3; --red: #c64343; --yellow: #8b6c0f;
  }}
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg); color: var(--fg);
  max-width: 900px; margin: 0 auto; padding: 2rem 1.5rem;
  line-height: 1.7;
}}
h1 {{ font-size: 1.8rem; margin-bottom: 0.5rem; color: var(--accent); }}
h2 {{ font-size: 1.4rem; margin-top: 2rem; margin-bottom: 0.8rem; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; }}
h3 {{ font-size: 1.15rem; margin-top: 1.5rem; margin-bottom: 0.5rem; }}
p {{ margin-bottom: 1rem; }}
ul, ol {{ margin-bottom: 1rem; padding-left: 1.5rem; }}
li {{ margin-bottom: 0.3rem; }}
blockquote {{
  border-left: 3px solid var(--accent); padding: 0.5rem 1rem;
  margin: 1rem 0; background: var(--bg2); border-radius: 0 6px 6px 0;
  color: var(--dim); font-style: italic;
}}
code {{
  background: var(--bg2); padding: 0.15rem 0.4rem; border-radius: 4px;
  font-family: "JetBrains Mono", "Fira Code", monospace; font-size: 0.9em;
}}
pre {{
  background: var(--bg2); border: 1px solid var(--border); border-radius: 8px;
  padding: 1rem; margin: 1rem 0; overflow-x: auto;
}}
pre code {{ background: none; padding: 0; }}
.mermaid {{
  background: var(--bg2); border-radius: 8px; padding: 1.5rem;
  margin: 1.5rem 0; text-align: center;
}}
.source {{ color: var(--dim); font-size: 0.9rem; margin-bottom: 2rem; }}
.nav {{
  position: fixed; bottom: 1rem; right: 1rem;
  background: var(--bg2); border: 1px solid var(--border);
  border-radius: 8px; padding: 0.5rem; display: flex; gap: 0.5rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}}
.nav button {{
  background: var(--accent); color: var(--bg); border: none;
  padding: 0.4rem 0.8rem; border-radius: 4px; cursor: pointer;
  font-size: 0.85rem;
}}
.nav button:hover {{ opacity: 0.85; }}
strong {{ color: var(--accent); }}
em {{ color: var(--yellow); }}
hr {{ border: none; border-top: 1px solid var(--border); margin: 2rem 0; }}
table {{
  width: 100%; border-collapse: collapse; margin: 1rem 0;
}}
th, td {{
  border: 1px solid var(--border); padding: 0.5rem 0.8rem; text-align: left;
}}
th {{ background: var(--bg2); font-weight: 600; }}
</style>
</head>
<body>
{body}
<div class="nav">
  <button onclick="location.href='#'">⬆ Top</button>
</div>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
mermaid.initialize({{
  startOnLoad: true,
  theme: window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'default',
  flowchart: {{ useMaxWidth: true }},
  sequence: {{ useMaxWidth: true }},
}});
</script>
</body>
</html>
"""


def markdown_to_html_body(md_text: str) -> str:
    """Convert Markdown to HTML body. Lightweight — handles common patterns."""
    lines = md_text.split("\n")
    html_parts: list[str] = []
    in_code = False
    in_mermaid = False
    code_lang = ""
    code_lines: list[str] = []
    in_list = False
    list_type = ""

    i = 0
    while i < len(lines):
        line = lines[i]

        # Code blocks
        if line.strip().startswith("```"):
            if in_mermaid:
                html_parts.append(f'<div class="mermaid">\n{"".join(l + chr(10) for l in code_lines)}</div>')
                in_mermaid = False
                i += 1
                continue
            if in_code:
                html_parts.append(f'<pre><code class="language-{code_lang}">{"".join(_esc(l) + chr(10) for l in code_lines)}</code></pre>')
                in_code = False
                i += 1
                continue
            lang = line.strip()[3:].strip()
            if lang == "mermaid":
                in_mermaid = True
                code_lines = []
            else:
                in_code = True
                code_lang = lang
                code_lines = []
            i += 1
            continue

        if in_code or in_mermaid:
            code_lines.append(line)
            i += 1
            continue

        # Close list if needed
        if in_list and not line.startswith("- ") and not line.startswith("* ") and not re.match(r"^\d+\. ", line):
            if in_list:
                html_parts.append(f"</{list_type}>")
                in_list = False

        # Headings
        if line.startswith("#"):
            m = re.match(r"^(#{1,6})\s+(.+)$", line)
            if m:
                level = len(m.group(1))
                text = _inline(m.group(2))
                slug = re.sub(r"[^\w-]", "", m.group(2).lower().replace(" ", "-"))
                html_parts.append(f'<h{level} id="{slug}">{text}</h{level}>')
                i += 1
                continue

        # Horizontal rule
        if line.strip() in ("---", "***", "___"):
            html_parts.append("<hr>")
            i += 1
            continue

        # Blockquote
        if line.startswith(">"):
            text = _inline(line[1:].strip())
            html_parts.append(f"<blockquote><p>{text}</p></blockquote>")
            i += 1
            continue

        # Unordered list
        if line.startswith("- ") or line.startswith("* "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
                list_type = "ul"
            text = _inline(line[2:].strip())
            html_parts.append(f"<li>{text}</li>")
            i += 1
            continue

        # Ordered list
        m = re.match(r"^\d+\.\s+(.+)$", line)
        if m:
            if not in_list:
                html_parts.append("<ol>")
                in_list = True
                list_type = "ol"
            text = _inline(m.group(1).strip())
            html_parts.append(f"<li>{text}</li>")
            i += 1
            continue

        # Table
        if "|" in line and i + 1 < len(lines) and re.match(r"^\|[-:|]+\|", lines[i + 1].strip()):
            table_lines = []
            while i < len(lines) and "|" in lines[i]:
                table_lines.append(lines[i])
                i += 1
            html_parts.append(_build_table(table_lines))
            continue

        # Paragraph
        if line.strip():
            html_parts.append(f"<p>{_inline(line)}</p>")

        i += 1

    if in_list:
        html_parts.append(f"</{list_type}>")

    return "\n".join(html_parts)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text: str) -> str:
    """Process inline Markdown: bold, italic, code, links."""
    text = _esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2" style="color:var(--accent)">\1</a>', text)
    return text


def _build_table(lines: list[str]) -> str:
    """Build an HTML table from Markdown table lines."""
    if len(lines) < 2:
        return ""
    headers = [c.strip() for c in lines[0].strip("|").split("|")]
    html = "<table><thead><tr>"
    for h in headers:
        html += f"<th>{_inline(h)}</th>"
    html += "</tr></thead><tbody>"
    for line in lines[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        html += "<tr>"
        for c in cells:
            html += f"<td>{_inline(c)}</td>"
        html += "</tr>"
    html += "</tbody></table>"
    return html


def generate_html_note(md_content: str, title: str, source: str, lang: str = "en") -> str:
    """Generate a self-contained HTML file from Markdown note content."""
    # Strip frontmatter if present
    content = md_content
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            content = content[end + 3:].strip()

    body = markdown_to_html_body(content)

    return _HTML_TEMPLATE.format(
        lang=lang,
        title=_esc(title),
        body=body,
    )


def has_mermaid_diagrams(md_content: str) -> bool:
    """Check if Markdown content contains Mermaid code blocks."""
    return bool(_MERMAID_BLOCK_RE.search(md_content))
