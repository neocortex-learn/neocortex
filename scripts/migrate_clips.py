"""Migrate existing clips: re-classify into topic subdirs + add takeaways.

Usage: .venv/bin/python scripts/migrate_clips.py [--dry-run]
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


async def main():
    dry_run = "--dry-run" in sys.argv

    from neocortex.clipper import CLIP_CATEGORIES, process_clip
    from neocortex.config import get_notes_dir, load_config, load_profile
    from neocortex.llm import create_provider
    from neocortex.models import Language

    cfg = load_config()
    profile = load_profile()
    notes_dir = get_notes_dir()
    clips_dir = notes_dir / "clips"

    provider = create_provider(cfg)

    md_files = sorted(clips_dir.glob("*.md"))
    print(f"Found {len(md_files)} clips to migrate")

    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8")
        fm_match = re.match(r"^---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
        if not fm_match:
            print(f"  SKIP (no frontmatter): {md_file.name}")
            continue

        fm_text = fm_match.group(1)
        body = fm_match.group(2).strip()

        fields = {}
        for line in fm_text.splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip()

        title = fields.get("title", md_file.stem)
        content_for_llm = body[:3000]

        try:
            result = await process_clip(
                content_for_llm, title, profile, provider, Language.ZH, notes_dir
            )
        except Exception as e:
            print(f"  ERROR: {md_file.name}: {e}")
            continue

        new_topic = result.get("topic", "ai-practice")
        takeaways = result.get("takeaways", [])
        new_summary = result.get("summary", "")

        print(f"  {md_file.name}")
        print(f"    topic: {fields.get('topic', '?')} -> {new_topic}")
        print(f"    takeaways: {len(takeaways)} items")

        if dry_run:
            continue

        new_fm_lines = []
        topic_updated = False
        summary_updated = False
        for line in fm_text.splitlines():
            if line.startswith("topic:"):
                new_fm_lines.append(f"topic: {new_topic}")
                topic_updated = True
            elif line.startswith("summary:") and new_summary and not fields.get("summary"):
                new_fm_lines.append(f"summary: {new_summary}")
                summary_updated = True
            else:
                new_fm_lines.append(line)
        if not topic_updated:
            new_fm_lines.append(f"topic: {new_topic}")

        new_body_parts = []
        if takeaways and "## 要点提炼" not in body:
            new_body_parts.append("## 要点提炼\n")
            for t in takeaways:
                new_body_parts.append(f"- {t}")
            new_body_parts.append("\n---\n")
        new_body_parts.append(body)

        new_text = "---\n" + "\n".join(new_fm_lines) + "\n---\n\n" + "\n".join(new_body_parts)

        target_dir = clips_dir / new_topic
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / md_file.name

        target_path.write_text(new_text, encoding="utf-8")
        md_file.unlink()
        print(f"    -> {target_path.relative_to(notes_dir)}")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
