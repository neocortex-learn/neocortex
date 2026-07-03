"""Clean junk from all existing clips."""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


async def main():
    dry_run = "--dry-run" in sys.argv

    from neocortex.clipper import clean_content
    from neocortex.config import get_notes_dir, load_config
    from neocortex.llm import create_provider

    cfg = load_config()
    provider = create_provider(cfg)
    notes_dir = get_notes_dir()
    clips_dir = notes_dir / "clips"

    all_files = sorted(clips_dir.rglob("*.md"))
    print(f"Scanning {len(all_files)} clips...\n")

    cleaned_count = 0
    for f in all_files:
        text = f.read_text("utf-8")
        m = re.match(r"^(---\n.*?\n---\n?)(.*)", text, re.DOTALL)
        if not m:
            continue

        header = m.group(1)
        body = m.group(2).strip()

        cleaned_body = await clean_content(body, provider)

        if cleaned_body != body:
            diff = len(body) - len(cleaned_body)
            rel = f.relative_to(notes_dir)
            print(f"  {rel} (-{diff} chars)")
            if not dry_run:
                f.write_text(header + "\n" + cleaned_body, encoding="utf-8")
            cleaned_count += 1

    print(f"\nDone: {cleaned_count} clips cleaned")


if __name__ == "__main__":
    asyncio.run(main())
