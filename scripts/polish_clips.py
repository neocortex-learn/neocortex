"""Polish all clips: fix titles, normalize formatting, delete junk.

Usage: .venv/bin/python scripts/polish_clips.py [--dry-run]
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

JUNK_INDICATORS = [
    "用户提供了一个空片段",
    "未包含任何可提取的内容",
    "neocortex clip --paste",
]


def is_junk(fm: dict, body: str) -> bool:
    title = fm.get("title", "")
    summary = fm.get("summary", "")
    for indicator in JUNK_INDICATORS:
        if indicator in title or indicator in summary or indicator in body[:200]:
            return True
    if len(body.strip()) < 30 and not fm.get("source", "").startswith("http"):
        return True
    return False


def needs_title_fix(fm: dict) -> bool:
    title = fm.get("title", "").strip()
    if not title:
        return True
    if re.match(r"^[0-9a-f]{6,}$", title):
        return True
    if title.startswith("# "):
        return True
    if len(title) > 40 and ("，" in title or "。" in title):
        return True
    if "这篇文章" in title or "介绍了" in title or "一份针对" in title:
        return True
    if "一种通过" in title or "这是一套" in title or "整理并保存" in title:
        return True
    return False


def parse_clip_file(path: Path) -> tuple[dict, str] | None:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
    if not m:
        return None
    fm_text = m.group(1)
    body = m.group(2).strip()
    fields = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            items = [i.strip().strip('"').strip("'") for i in val[1:-1].split(",") if i.strip()]
            fields[key] = items
        else:
            fields[key] = val.strip('"').strip("'")
    return fields, body


def rebuild_body(fm: dict, body: str, takeaways: list[str] | None = None) -> str:
    """Rebuild body with standard structure: takeaways → source → content."""
    existing_takeaways = []
    rest_body = body

    ta_match = re.match(r"^## 要点提炼\s*\n(.*?)\n---\s*\n(.*)", body, re.DOTALL)
    if ta_match:
        ta_section = ta_match.group(1).strip()
        rest_body = ta_match.group(2).strip()
        existing_takeaways = [line.lstrip("- ").strip() for line in ta_section.splitlines() if line.strip().startswith("-")]

    final_takeaways = takeaways if takeaways else existing_takeaways

    source = fm.get("source", "")
    source_line = ""
    if source and source.startswith("http"):
        source_line = f"\n> 原文：<{source}>\n"
        rest_body = re.sub(r"^>\s*原文[：:]\s*<[^>]+>\s*\n?", "", rest_body, flags=re.MULTILINE)

    parts = []
    if final_takeaways:
        parts.append("## 要点提炼\n")
        for t in final_takeaways:
            parts.append(f"- {t}")
        parts.append("\n---\n")

    if source_line:
        parts.append(source_line)

    parts.append(rest_body)
    return "\n".join(parts)


def write_clip(path: Path, fm: dict, body: str):
    fm_lines = ["---"]
    key_order = ["id", "source", "title", "clip_type", "auto_tags", "related_concepts",
                 "status", "summary", "relevance", "priority", "topic",
                 "created_at", "processed_at", "promoted_to", "next_surface", "surface_count"]
    for key in key_order:
        if key not in fm:
            continue
        val = fm[key]
        if isinstance(val, list):
            val_str = "[" + ", ".join(f'"{v}"' for v in val) + "]"
        else:
            val_str = str(val)
        fm_lines.append(f"{key}: {val_str}")
    fm_lines.append("---")
    content = "\n".join(fm_lines) + "\n\n" + body
    path.write_text(content, encoding="utf-8")


def make_slug(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title)
    slug = re.sub(r"[\s_]+", "-", slug).strip("-").lower()[:50]
    return slug


async def generate_title(content: str, summary: str, provider) -> str:
    prompt = (
        "Based on the content below, generate a SHORT, descriptive Chinese title (10-20 chars). "
        "The title should capture the core topic. No quotes, no markdown, no punctuation at the end.\n\n"
        f"Summary: {summary}\n\n"
        f"Content excerpt:\n{content[:1500]}\n\n"
        "Reply with ONLY the title, nothing else."
    )
    raw = await provider.chat([{"role": "user", "content": prompt}])
    return raw.strip().strip('"').strip("#").strip()


async def main():
    dry_run = "--dry-run" in sys.argv

    from neocortex.config import load_config, load_profile, get_notes_dir
    from neocortex.llm import create_provider

    cfg = load_config()
    notes_dir = get_notes_dir()
    clips_dir = notes_dir / "clips"
    provider = create_provider(cfg)

    all_files = sorted(clips_dir.rglob("*.md"))
    print(f"Scanning {len(all_files)} clips...\n")

    deleted = 0
    fixed = 0

    for path in all_files:
        result = parse_clip_file(path)
        if result is None:
            continue
        fm, body = result
        rel = path.relative_to(notes_dir)

        if is_junk(fm, body):
            print(f"  DELETE: {rel}")
            if not dry_run:
                path.unlink()
            deleted += 1
            continue

        changed = False
        old_title = fm.get("title", "")

        if old_title.startswith("# "):
            fm["title"] = old_title.lstrip("# ").strip()
            changed = True

        if needs_title_fix(fm):
            summary = fm.get("summary", "")
            new_title = await generate_title(body, summary, provider)
            if new_title and len(new_title) > 2:
                print(f"  TITLE: {rel}")
                print(f"    '{old_title}' -> '{new_title}'")
                fm["title"] = new_title
                changed = True

        new_body = rebuild_body(fm, body)
        if new_body != body:
            changed = True

        if changed:
            if not dry_run:
                write_clip(path, fm, new_body)

                new_slug = make_slug(fm["title"])
                date = fm.get("created_at", "undated")
                new_name = f"{date}-{new_slug}.md" if new_slug else path.name
                if new_name != path.name:
                    new_path = path.parent / new_name
                    if not new_path.exists():
                        path.rename(new_path)
                        print(f"    -> {new_path.relative_to(notes_dir)}")

            fixed += 1

    print(f"\nDone: {deleted} deleted, {fixed} fixed")


if __name__ == "__main__":
    asyncio.run(main())
