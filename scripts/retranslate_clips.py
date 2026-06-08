"""Re-translate English clips using baoyu-style translation.

Usage: .venv/bin/python scripts/retranslate_clips.py [--dry-run]
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


async def main():
    dry_run = "--dry-run" in sys.argv

    from neocortex.clipper import _chinese_ratio, maybe_translate_to_chinese
    from neocortex.config import get_notes_dir, load_config
    from neocortex.llm import create_provider

    cfg = load_config()
    provider = create_provider(cfg)
    notes_dir = get_notes_dir()
    clips_dir = notes_dir / "clips"

    targets = []
    for f in sorted(clips_dir.rglob("*.md")):
        text = f.read_text("utf-8")
        m = re.match(r"^---\n(.*?)\n---\n?(.*)", text, re.DOTALL)
        if not m:
            continue
        fm_text = m.group(1)
        body = m.group(2).strip()

        body_no_takeaways = re.sub(
            r"^## 要点提炼.*?---", "", body, count=1, flags=re.DOTALL
        ).strip()
        if _chinese_ratio(body_no_takeaways) < 0.20:
            targets.append((f, fm_text, body, body_no_takeaways))

    print(f"Found {len(targets)} English clips to translate\n")

    for f, fm_text, body, content_to_translate in targets:
        rel = f.relative_to(notes_dir)
        print(f"  Translating: {rel}")

        if dry_run:
            continue

        translated = await maybe_translate_to_chinese(
            content_to_translate, provider, threshold=0.99
        )
        if not translated:
            print("    SKIP: translation returned None")
            continue

        ta_match = re.match(r"^(## 要点提炼.*?---\s*\n)(.*)", body, re.DOTALL)
        if ta_match:
            takeaways_section = ta_match.group(1)
            new_body = takeaways_section + translated
        else:
            new_body = translated

        new_text = "---\n" + fm_text + "\n---\n\n" + new_body
        f.write_text(new_text, encoding="utf-8")
        print(f"    OK ({len(translated)} chars)")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
