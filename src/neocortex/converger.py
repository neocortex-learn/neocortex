"""Knowledge convergence — synthesize accumulated notes into higher-level understanding."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from neocortex.llm.base import LLMProvider
from neocortex.models import Language, Profile


def gather_recent_notes(notes_dir: Path, days: int = 7) -> list[dict]:
    """Gather notes from the last N days. Returns [{filename, title, date, content_preview}]."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    notes = []
    for f in sorted(notes_dir.rglob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        if "diagrams" in f.parts:
            continue
        mtime = date.fromtimestamp(f.stat().st_mtime).isoformat()
        if mtime < cutoff:
            continue
        content = f.read_text(encoding="utf-8")
        title_match = re.search(r'^title:\s*"?(.+?)"?\s*$', content, re.MULTILINE)
        if not title_match:
            title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else f.stem
        preview = content
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                preview = content[end + 3 :].strip()
        preview = preview[:2000]
        notes.append({"filename": f.name, "title": title, "date": mtime, "content": preview})
    return notes


def detect_cadence(notes: list[dict]) -> str:
    """Detect appropriate cadence: flash (<=5 notes), weekly (6-20), monthly (21+)."""
    if len(notes) <= 5:
        return "flash"
    if len(notes) <= 20:
        return "weekly"
    return "monthly"


async def generate_convergence_report(
    notes: list[dict],
    cadence: str,
    profile: Profile,
    provider: LLMProvider,
    language: Language = Language.EN,
) -> str:
    """Generate a convergence report from accumulated notes."""
    lang_inst = "用中文输出。" if language == Language.ZH else "Output in English."

    notes_summary = ""
    for n in notes:
        notes_summary += f"\n### {n['title']} ({n['date']})\n{n['content']}\n"

    cadence_instruction = {
        "flash": "This is a quick flash review of the last few notes. Be concise — find connections and key takeaways.",
        "weekly": "This is a weekly convergence. Identify themes, cross-topic connections, and knowledge gaps across the week's learning.",
        "monthly": "This is a monthly synthesis. Tell a narrative of how the reader's understanding evolved. Identify blind spots and suggest direction.",
    }

    persona = profile.persona
    role = persona.role.value if persona.role else "developer"
    goal = persona.learning_goal.value if persona.learning_goal else "level up"

    prompt = f"""\
You are a learning coach synthesizing a reader's accumulated knowledge.

Reader: {role}, goal: {goal}
Cadence: {cadence} ({len(notes)} notes)
{cadence_instruction.get(cadence, cadence_instruction["weekly"])}

Notes from this period:
{notes_summary}

Generate a convergence report with these sections:

## Retrieval Check
Pose 2-3 questions the reader should try to answer FROM MEMORY before reading on.
These should test understanding, not recall — "why" and "how" questions, not "what is".

## Themes Discovered
Identify 2-4 themes that emerge across multiple notes. For each theme:
- Name it concisely
- Show which notes contribute to it
- Explain the insight that only becomes visible when you connect them

## Cross-Topic Connections
Find surprising connections between seemingly unrelated notes.
Use the "transform" technique: morph concept A into concept B step by step.

## Learning Trajectory
How did the reader's understanding evolve over this period?
What shifted from "how to do X" to "why X works this way"?

## Knowledge Gaps Detected
Topics mentioned but not covered. Areas where understanding seems surface-level.
Concepts that keep appearing but haven't been deeply explored.

## Suggested Next Steps
Based on convergence patterns, what should the reader explore next?

Writing rules:
- Be a thoughtful mentor, not a summarizer
- Show reasoning: "Since you learned X and Y, this suggests Z"
- Use the reader's own project context for analogies
- Include Mermaid diagrams where they help (mindmap for themes, flowchart for trajectory)
- Be honest about gaps

{lang_inst}"""

    messages = [
        {"role": "system", "content": "You are a learning coach who helps people synthesize knowledge. Output Markdown."},
        {"role": "user", "content": prompt},
    ]

    return await provider.chat(messages)
