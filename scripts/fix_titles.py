"""Fix English titles to Chinese."""
from __future__ import annotations
import os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from neocortex.config import get_notes_dir

TITLE_MAP = {
    "LLM Powered Autonomous Agents": "LLM驱动自主智能体",
    "Domain Expertise Has Always Been the Real Moat": "领域专长始终是核心竞争力",
    "What to Learn, Build, and Skip in AI Agents (2026)": "AI智能体自学指南（2026）",
    "A Practical Guide to Becoming an AI-Native Engineer": "成为AI原生工程师实践指南",
    "Every Agentic Engineering Hack I Know (June 2026)": "智能体工程技巧合集（2026年6月）",
    "# Every Agentic Engineering Hack I Know (June 2026)": "智能体工程技巧合集（2026年6月）",
    "One Line of Code on Every Other Platform. Why Can't the Web Do It After 30 Years?": "一行代码实现跨平台功能，网页为何30年做不到？",
    "Claude 3.7 Sonnet and Claude Code": "Claude 3.7 Sonnet与Claude Code",
}

def make_slug(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title)
    slug = re.sub(r"[\s_]+", "-", slug).strip("-").lower()[:50]
    return slug

notes_dir = get_notes_dir()
clips_dir = notes_dir / "clips"

for f in sorted(clips_dir.rglob("*.md")):
    text = f.read_text("utf-8")
    m = re.search(r"^title: (.+)$", text, re.MULTILINE)
    if not m:
        continue
    old_title = m.group(1).strip()
    if old_title not in TITLE_MAP:
        continue
    new_title = TITLE_MAP[old_title]
    new_text = text.replace(f"title: {old_title}", f"title: {new_title}", 1)
    f.write_text(new_text, encoding="utf-8")

    date_m = re.search(r"^created_at: (.+)$", new_text, re.MULTILINE)
    date = date_m.group(1).strip() if date_m else "undated"
    new_slug = make_slug(new_title)
    new_name = f"{date}-{new_slug}.md"
    if new_name != f.name:
        new_path = f.parent / new_name
        if not new_path.exists():
            f.rename(new_path)
            print(f"  {f.name} -> {new_name}")
        else:
            print(f"  {f.name}: target exists, title updated only")
    else:
        print(f"  {f.name}: title updated")
