"""Tests for visual note renderer — HTML generation from Markdown + Mermaid."""

from __future__ import annotations

from neocortex.reader.visual import (
    generate_html_note,
    has_mermaid_diagrams,
    markdown_to_html_body,
)


class TestHasMermaidDiagrams:
    def test_detects_mermaid(self):
        md = "Some text\n```mermaid\nflowchart LR\n  A --> B\n```\nMore text"
        assert has_mermaid_diagrams(md) is True

    def test_no_mermaid(self):
        md = "Some text\n```python\nprint('hi')\n```\nMore text"
        assert has_mermaid_diagrams(md) is False

    def test_empty(self):
        assert has_mermaid_diagrams("") is False

    def test_multiple_mermaid(self):
        md = "```mermaid\nflowchart\n```\ntext\n```mermaid\nsequenceDiagram\n```"
        assert has_mermaid_diagrams(md) is True


class TestMarkdownToHtml:
    def test_heading(self):
        html = markdown_to_html_body("# Hello World")
        assert "<h1" in html
        assert "Hello World" in html

    def test_heading_levels(self):
        html = markdown_to_html_body("## Sub\n### Sub-sub")
        assert "<h2" in html
        assert "<h3" in html

    def test_paragraph(self):
        html = markdown_to_html_body("Just a paragraph.")
        assert "<p>" in html

    def test_bold(self):
        html = markdown_to_html_body("This is **bold** text.")
        assert "<strong>bold</strong>" in html

    def test_italic(self):
        html = markdown_to_html_body("This is *italic* text.")
        assert "<em>italic</em>" in html

    def test_inline_code(self):
        html = markdown_to_html_body("Use `print()` here.")
        assert "<code>print()</code>" in html

    def test_code_block(self):
        html = markdown_to_html_body("```python\nprint('hi')\n```")
        assert "<pre>" in html
        assert "print" in html

    def test_mermaid_block(self):
        md = "```mermaid\nflowchart LR\n  A --> B\n```"
        html = markdown_to_html_body(md)
        assert 'class="mermaid"' in html
        assert "flowchart LR" in html

    def test_unordered_list(self):
        html = markdown_to_html_body("- item 1\n- item 2")
        assert "<ul>" in html
        assert "<li>" in html
        assert "item 1" in html

    def test_ordered_list(self):
        html = markdown_to_html_body("1. first\n2. second")
        assert "<ol>" in html
        assert "<li>" in html

    def test_blockquote(self):
        html = markdown_to_html_body("> This is a quote")
        assert "<blockquote>" in html

    def test_horizontal_rule(self):
        html = markdown_to_html_body("text\n---\nmore")
        assert "<hr>" in html

    def test_link(self):
        html = markdown_to_html_body("[click](https://example.com)")
        assert "href=" in html
        assert "click" in html

    def test_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        html = markdown_to_html_body(md)
        assert "<table>" in html
        assert "<th>" in html
        assert "<td>" in html

    def test_escapes_html(self):
        html = markdown_to_html_body("Use <script> tags")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


class TestGenerateHtmlNote:
    def test_basic_generation(self):
        md = "# Test\n\nSome content."
        html = generate_html_note(md, "Test", "https://example.com")
        assert "<!DOCTYPE html>" in html
        assert "Test" in html
        assert "mermaid" in html  # mermaid.js script included

    def test_strips_frontmatter(self):
        md = "---\ntitle: test\ndate: 2026-03-22\n---\n\n# Actual Content"
        html = generate_html_note(md, "Test", "source")
        assert "Actual Content" in html
        assert "title: test" not in html

    def test_mermaid_rendered(self):
        md = "# Topic\n\n```mermaid\nflowchart LR\n  A --> B\n```\n\nExplanation."
        html = generate_html_note(md, "Topic", "source")
        assert 'class="mermaid"' in html
        assert "flowchart LR" in html

    def test_dark_theme_support(self):
        html = generate_html_note("# Test", "Test", "source")
        assert "prefers-color-scheme" in html

    def test_lang_attribute(self):
        html = generate_html_note("# Test", "Test", "source", lang="zh")
        assert 'lang="zh"' in html

    def test_self_contained(self):
        """HTML should be self-contained — only external dep is mermaid CDN."""
        html = generate_html_note("# Test", "Test", "source")
        assert "<style>" in html  # CSS is inline
        assert "cdn.jsdelivr.net/npm/mermaid" in html  # Mermaid via CDN


class TestFullPipeline:
    """Test the full pipeline: Markdown with Mermaid → HTML with rendered diagrams."""

    def test_realistic_note(self):
        md = """\
---
title: "Two-Phase Commit"
source: "https://example.com/ddia"
date: 2026-03-22
tags:
  - distributed-systems
---

# Two-Phase Commit Protocol

> Source: https://example.com/ddia

```mermaid
mindmap
  root((Two-Phase Commit))
    Deep Dive
      Prepare Phase
      Commit Phase
    Review
      Failure Handling
```

## Prepare Phase

The coordinator sends a **prepare** message to all participants.

```mermaid
sequenceDiagram
    Coordinator->>Node A: Prepare
    Coordinator->>Node B: Prepare
    Node A-->>Coordinator: OK
    Node B-->>Coordinator: OK
```

Each node checks if it can commit and responds.

## Commit Phase

Once all nodes respond OK, the coordinator sends **commit**.

```mermaid
sequenceDiagram
    Coordinator->>Node A: Commit
    Coordinator->>Node B: Commit
    Node A-->>Coordinator: ACK
    Node B-->>Coordinator: ACK
```

## Failure Handling

If any node responds with ABORT:

```mermaid
stateDiagram-v2
    [*] --> Preparing
    Preparing --> Committed: All OK
    Preparing --> Aborted: Any ABORT
    Committed --> [*]
    Aborted --> [*]
```

### Action Items

1. Review your project's transaction handling
2. Check if you need distributed transactions
"""
        assert has_mermaid_diagrams(md)

        html = generate_html_note(md, "Two-Phase Commit", "https://example.com/ddia")

        # Structure
        assert "<!DOCTYPE html>" in html
        assert "Two-Phase Commit Protocol" in html

        # All 4 Mermaid diagrams present
        assert html.count('class="mermaid"') == 4

        # Content preserved
        assert "Prepare Phase" in html
        assert "Commit Phase" in html
        assert "Failure Handling" in html
        assert "Action Items" in html

        # Sequence diagram content
        assert "Coordinator" in html
        assert "Node A" in html

        # State diagram content
        assert "Preparing" in html
        assert "Committed" in html
        assert "Aborted" in html

        # Frontmatter stripped
        assert "tags:" not in html

        # Self-contained
        assert "mermaid.min.js" in html
