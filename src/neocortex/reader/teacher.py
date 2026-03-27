"""Personalized note generation — outline analysis and note writing."""

from __future__ import annotations

import json

from neocortex.llm.base import LLMProvider
from neocortex.models import Language, LearningStyle, Outline, OutlineItem, Profile
from neocortex.reader.chunker import Chunk, chunk_content
from neocortex.reader.fetcher import Document


def _profile_summary(profile: Profile) -> str:
    data = profile.model_dump(exclude_none=True, exclude_defaults=True)
    return json.dumps(data, ensure_ascii=False, indent=2)


def _section_titles(doc: Document) -> str:
    lines: list[str] = []
    for section in doc.sections:
        indent = "  " * (section.level - 1)
        title = section.title or "(untitled section)"
        lines.append(f"{indent}- {title}")
    return "\n".join(lines) if lines else doc.title


def _language_instruction(profile: Profile) -> str:
    lang = profile.persona.language
    if lang == Language.ZH:
        return "请用中文输出。"
    return "Output in English."


def _level_instruction(profile: Profile) -> str:
    offset = profile.calibration.level_offset
    if offset >= 2:
        return "The reader finds the content too easy. Significantly increase depth and complexity. Skip basic explanations entirely."
    if offset == 1:
        return "The reader prefers slightly more advanced content. Increase depth and assume stronger fundamentals."
    if offset == -1:
        return "The reader prefers simpler explanations. Add more context and explain more fundamentals."
    if offset <= -2:
        return "The reader finds the content too hard. Significantly simplify explanations. Break down concepts into smaller steps."
    return ""


def _style_instruction(profile: Profile) -> str:
    style = profile.persona.learning_style
    if style is None:
        return ""
    mapping = {
        LearningStyle.CODE_EXAMPLES: "Use real code examples to illustrate every concept. Show before-and-after code when possible.",
        LearningStyle.THEORY_FIRST: "Start with theory and principles. Explain the 'why' before showing any implementation.",
        LearningStyle.JUST_DO_IT: "Be concise and actionable. Skip lengthy explanations, focus on what to do and how.",
        LearningStyle.COMPARE_WITH_KNOWN: "Compare new concepts with things the reader already knows. Use analogies from their existing projects.",
    }
    inst = mapping.get(style, "")
    return f"\nTeaching style: {inst}" if inst else ""


async def generate_outline(
    doc: Document,
    profile: Profile,
    provider: LLMProvider,
) -> Outline:
    profile_json = _profile_summary(profile)
    titles = _section_titles(doc)
    lang_inst = _language_instruction(profile)
    level_inst = _level_instruction(profile)

    system_prompt = f"""\
You are a technical advisor who knows the reader's background.

Reader profile:
{profile_json}

Below are the chapter/section titles of the content the reader is about to read:
{titles}

Analyze each section against the reader's skill profile and mark:
- "skip": Content the reader has already mastered (summarize in one sentence)
- "brief": Content the reader should know but doesn't need deep explanation
- "deep": Knowledge gaps or key areas the reader needs to focus on

{level_inst}

Output valid JSON with this exact structure:
{{
  "items": [
    {{"title": "section title", "marker": "skip|brief|deep", "reason": "why this marking"}}
  ]
}}

{lang_inst}"""

    messages = [
        {"role": "user", "content": system_prompt},
    ]

    response = await provider.chat(messages, json_mode=True)

    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(response[start:end])
            except json.JSONDecodeError:
                raise ValueError(f"Failed to parse outline from LLM response")
        else:
            raise ValueError(f"Failed to parse outline from LLM response")

    items: list[OutlineItem] = []
    for raw_item in data.get("items", []):
        marker = raw_item.get("marker", "brief")
        if marker not in ("skip", "brief", "deep"):
            marker = "brief"
        items.append(OutlineItem(
            title=raw_item.get("title", ""),
            marker=marker,
            reason=raw_item.get("reason", ""),
        ))

    return Outline(source=doc.source, items=items)


def _build_chunk_prompt(
    chunk: Chunk,
    outline: Outline,
    profile: Profile,
    focus: str | None,
    question: str | None,
) -> str:
    profile_json = _profile_summary(profile)
    lang_inst = _language_instruction(profile)
    level_inst = _level_instruction(profile)
    style_inst = _style_instruction(profile)

    marker_map: dict[str, str] = {}
    for item in outline.items:
        marker_map[item.title] = item.marker

    chunk_marker = marker_map.get(chunk.title)
    if chunk_marker is None:
        for item_title, marker in marker_map.items():
            if len(item_title) >= 5 and (item_title in chunk.title or chunk.title in item_title):
                chunk_marker = marker
                break
    if chunk_marker is None:
        chunk_marker = "brief"

    if chunk_marker == "skip":
        depth_instruction = (
            "This section covers content the reader already masters. "
            "Provide only a one-sentence summary. Do not elaborate."
        )
    elif chunk_marker == "brief":
        depth_instruction = (
            "This section covers content the reader should know. "
            "Provide a clear explanation with key principles. Keep it concise but complete."
        )
    else:
        depth_instruction = (
            "This is a KEY LEARNING AREA for this reader. "
            "Provide detailed explanation. Use analogies from the reader's own projects when possible. "
            "Include concrete examples. End with Action Items the reader can apply to their own work."
        )

    focus_instruction = ""
    if focus:
        focus_instruction = f"\nThe reader has specifically asked to focus on: **{focus}**. Emphasize this topic throughout."

    question_instruction = ""
    if question:
        question_instruction = f"\nThe reader has a specific question: **{question}**. Address this question at the end of the notes."

    prev_context = ""
    if chunk.prev_summary:
        prev_context = f"\nContext from previous section:\n{chunk.prev_summary}\n"

    prompt = f"""\
You are a technical advisor who knows the reader's background.

Reader profile:
{profile_json}

{depth_instruction}

{level_inst}{style_inst}
{prev_context}
The reader is reading the following content (section: {chunk.position}):

---
{chunk.content}
---
{focus_instruction}
{question_instruction}

Generate personalized study notes for this section.

Content requirements:
1. Skip concepts the reader already masters — don't waste space on them
2. For areas the reader has experience in, use analogies from their own projects
3. Expand on the reader's knowledge gaps (the "gaps" in their profile)
4. If this is a deep-dive section, include Action Items: specific, actionable improvements for the reader's own projects
5. Keep difficulty at the reader's current level +1 to +2 — stretch but don't overwhelm

Writing principles (non-negotiable):
- Colloquial test: would you explain it this way to a friend? If not, rewrite
- Zero jargon first: explain in plain language, THEN mention the technical term
- Show reasoning: simulate the process of figuring it out, not the result of having figured it out. "Since A is B, could C also be D?" — walk the reader through the logic
- Transform, don't define: to explain the relationship between A and B, morph A into B step by step. "Turn LSTM into ResNet" is 10x better than "LSTM and ResNet are dual"
- Land on actionable: end with "this means you can ___", not "this makes us rethink ___"
- One idea per sentence. Short words over long words. Cut filler
- Be honest: if the content has flaws, say so. If something is unclear, say so

Visual diagrams (Mermaid):
- Use ```mermaid code blocks (the reader's Markdown tool renders them)
- mindmap for topic overviews, flowchart for processes, sequenceDiagram for interactions, classDiagram for structures, stateDiagram-v2 for lifecycles
- Place each diagram RIGHT AFTER its related text (spatial contiguity)
- Every diagram must serve a purpose — no decorative diagrams
- Deep-dive sections: aim for 1-2 diagrams. Brief sections: optional

Output format: Markdown with clear heading hierarchy and Mermaid diagrams. Suitable for future review.

{lang_inst}"""

    return prompt


async def generate_notes(
    doc: Document,
    outline: Outline,
    profile: Profile,
    provider: LLMProvider,
    focus: str | None = None,
    question: str | None = None,
    deep: bool = False,
) -> str:
    max_ctx = provider.max_context_tokens()
    reserved_for_prompt = 2000
    reserved_for_response = max(max_ctx // 4, 4000)
    max_chunk_tokens = max_ctx - reserved_for_prompt - reserved_for_response
    max_chunk_tokens = max(max_chunk_tokens, 2000)

    chunks = chunk_content(doc, max_tokens=max_chunk_tokens)

    note_parts: list[str] = []
    lang = profile.persona.language
    if lang == Language.ZH:
        header = f"# {doc.title}\n\n> 来源: {doc.source}\n"
    else:
        header = f"# {doc.title}\n\n> Source: {doc.source}\n"

    # Generate topic overview mindmap from outline
    deep_items = [i for i in outline.items if i.marker == "deep" and i.title]
    brief_items = [i for i in outline.items if i.marker == "brief" and i.title]
    if deep_items or brief_items:
        mindmap_lines = ["```mermaid", "mindmap", f"  root(({doc.title[:40]}))"]
        if deep_items:
            label = "重点学习" if lang == Language.ZH else "Deep Dive"
            mindmap_lines.append(f"    {label}")
            for item in deep_items[:6]:
                safe = item.title.replace("(", "").replace(")", "")[:30]
                mindmap_lines.append(f"      {safe}")
        if brief_items:
            label = "快速回顾" if lang == Language.ZH else "Review"
            mindmap_lines.append(f"    {label}")
            for item in brief_items[:6]:
                safe = item.title.replace("(", "").replace(")", "")[:30]
                mindmap_lines.append(f"      {safe}")
        mindmap_lines.append("```")
        header += "\n" + "\n".join(mindmap_lines) + "\n"

    note_parts.append(header)

    for chunk in chunks:
        prompt = _build_chunk_prompt(chunk, outline, profile, focus, question)
        messages = [{"role": "user", "content": prompt}]
        response = await provider.chat(messages)
        note_parts.append(response.strip())

    if question:
        already_answered = any(question.lower() in part.lower() for part in note_parts)
        if not already_answered:
            q_prompt = _build_question_section(question, doc, profile)
            messages = [{"role": "user", "content": q_prompt}]
            response = await provider.chat(messages)
            note_parts.append(response.strip())

    if deep:
        anatomy_prompt = _build_anatomy_prompt(doc, profile)
        messages = [{"role": "user", "content": anatomy_prompt}]
        response = await provider.chat(messages)
        note_parts.append(response.strip())

    return "\n\n---\n\n".join(note_parts)


def _build_anatomy_prompt(doc: Document, profile: Profile) -> str:
    """Build a prompt for deep concept anatomy (8 dimensions)."""
    lang_inst = _language_instruction(profile)
    profile_json = _profile_summary(profile)

    return f"""\
You are a concept anatomist who helps a reader deeply understand the core ideas in what they just read.

Reader profile:
{profile_json}

The reader just read: "{doc.title}" (source: {doc.source})

Perform a deep concept anatomy on the most important concept from this content.
Cut it open from 8 angles, then compress it into an insight.

## Steps:

### 1. Anchor
- What is the most common definition? What are the common misconceptions?
- What are the core components hidden inside this concept?

### 2. Eight Cuts (2-3 sentences each, only the essentials)
1. **History**: Where did it first emerge → how did it evolve → what turning point made it what it is today
2. **Dialectics**: What is its opposite → what higher understanding emerges from the collision
3. **Phenomenology**: Drop all assumptions, return to the thing itself → use one everyday scenario to reconstruct it
4. **Language**: Etymology (Chinese/English/Greek/Latin) → draw the semantic web of related concepts → what metaphor is hidden in this word
5. **Formalization**: Write a formula or formal expression → where does the formula break down
6. **Existential**: How did this concept change how people live
7. **Aesthetics**: What is beautiful about it? Use one concrete image to present it
8. **Meta-reflection**: What metaphor are we using to understand it? What does this metaphor hide? What if we switched metaphors

### 3. Introspection
1. Become this concept. See the world in first person. 3-5 sentences.
2. Which of the eight cuts point to the same deep structure? Extract it.

### 4. Compression
1. **Formula**: `Concept = ...`
2. **One sentence**: The deepest understanding in the simplest words
3. **Structure diagram**: Pure ASCII diagram showing the concept's skeleton

Output format: Markdown with ## headings for each step.

{lang_inst}"""


def _build_question_section(
    question: str,
    doc: Document,
    profile: Profile,
) -> str:
    profile_json = _profile_summary(profile)
    lang_inst = _language_instruction(profile)

    return f"""\
You are a technical advisor who knows the reader's background.

Reader profile:
{profile_json}

The reader just read: "{doc.title}" (source: {doc.source})

The reader has this specific question:
**{question}**

Please answer this question in the context of what the reader just read, considering their skill level and project experience. Be specific and actionable.

Output format: Markdown, starting with a "## Q&A" heading.

{lang_inst}"""
