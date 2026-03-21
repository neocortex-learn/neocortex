"""Learning path recommender — suggests what to learn next based on your profile."""

from __future__ import annotations

import json
import re

from neocortex.llm.base import LLMProvider
from neocortex.models import Language, Profile, Recommendation, RecommendationRecord, Resource


def _extract_gaps(profile: Profile) -> list[dict]:
    """Extract all skill gaps with their parent domain/integration and level."""
    gaps: list[dict] = []
    for name, skill in profile.skills.domains.items():
        for gap in skill.gaps:
            gaps.append({"gap": gap, "domain": name, "level": skill.level.value})
    for name, skill in profile.skills.integrations.items():
        for gap in skill.gaps:
            gaps.append({"gap": gap, "domain": name, "level": skill.level.value})
    return gaps


def _build_context(
    profile: Profile,
    records: list[RecommendationRecord] | None = None,
) -> str:
    """Build a structured context string for the LLM prompt."""
    sections: list[str] = []

    persona = profile.persona
    sections.append(
        "## Learner\n"
        f"- Role: {persona.role.value if persona.role else 'unknown'}\n"
        f"- Experience: {persona.experience_years.value if persona.experience_years else 'unknown'} years\n"
        f"- Learning style: {persona.learning_style.value if persona.learning_style else 'unknown'}\n"
        f"- Learning goal: {persona.learning_goal.value if persona.learning_goal else 'unknown'}"
    )

    gaps = _extract_gaps(profile)
    if gaps:
        grouped: dict[str, list[str]] = {}
        for g in gaps:
            key = f"{g['domain']} ({g['level']})"
            grouped.setdefault(key, []).append(g["gap"])
        lines = [f"- {key}: {', '.join(names)}" for key, names in grouped.items()]
        sections.append("## Skill gaps\n" + "\n".join(lines))

    if records:
        completed = [r for r in records if r.status == "completed"][-10:]
        if completed:
            lines = [f"- {r.topic}" for r in completed]
            sections.append("## Recently completed\n" + "\n".join(lines))

    topics_read = profile.learning_history.topics_read[-10:]
    if topics_read:
        lines = [f"- {tr.title}" for tr in topics_read]
        sections.append("## Recently read\n" + "\n".join(lines))

    return "\n\n".join(sections)


_PROMPT_ZH = """你是一个资深技术导师。根据以下开发者画像，设计一条包含 {count} 步的学习路径。

{context}

设计原则：
1. 按学习顺序排列——基础在前，进阶在后，每一步尽量建立在前面的基础上
2. 优先补盲区（gaps）
3. 结合学习目标（learning_goal）
4. 考虑已完成和已读内容——不要推荐已经在学的
5. 难度匹配——基于当前水平推荐 +1~+2 级别的内容

对每一步，提供：
- step: 学习顺序编号（从 1 开始）
- topic: 具体的学习主题
- reason: 为什么在这一步学这个
- resources: 2-3 个学习资源（格式 {{"title": "...", "url": "...", "type": "article"}}）
- expected_benefit: 学完后的收益
- priority: high / medium / low
- related_gaps: 对应的 gap 名称列表
- depends_on: 前置步骤的 topic 名称列表（如果没有前置则为空数组）

用中文回答。输出 JSON 数组格式，按 step 排序。"""

_PROMPT_EN = """You are a senior technical mentor. Based on the developer profile below, design a learning path with {count} steps.

{context}

Principles:
1. Arrange in learning order — fundamentals first, advanced later, each step builds on previous ones where possible
2. Prioritize filling gaps
3. Align with learning_goal
4. Consider completed and recently read content — don't repeat
5. Difficulty match — recommend +1~+2 levels above current

For each step, provide:
- step: learning order number (starting from 1)
- topic: specific learning topic
- reason: why learn this at this step
- resources: 2-3 resources (each as {{"title": "...", "url": "...", "type": "article"}})
- expected_benefit: what you gain after learning
- priority: high / medium / low
- related_gaps: list of gap names this addresses
- depends_on: list of prerequisite topic names from earlier steps (empty array if none)

Output as a JSON array, sorted by step."""


async def generate_recommendations(
    profile: Profile,
    provider: LLMProvider,
    count: int = 5,
    language: Language = Language.EN,
    records: list[RecommendationRecord] | None = None,
) -> list[Recommendation]:
    context = _build_context(profile, records)

    template = _PROMPT_ZH if language == Language.ZH else _PROMPT_EN
    prompt = template.format(count=count, context=context)

    system_msg = "You are a technical learning advisor. Always respond in valid JSON only."
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt},
    ]

    response = await provider.chat(messages, json_mode=False)

    gap_names = {g["gap"] for g in _extract_gaps(profile)}
    return _parse_recommendations(response, count, gap_names)


_VALID_PRIORITIES = {"high", "medium", "low"}


def _parse_recommendations(
    text: str,
    max_count: int,
    gap_names: set[str] | None = None,
) -> list[Recommendation]:
    if not text or not text.strip():
        return []

    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[1:end])

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = _extract_json_fragment(text)
        if data is None:
            return []

    if isinstance(data, dict):
        for key in ("recommendations", "items", "topics"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            data = [data]

    if not isinstance(data, list):
        return []

    results = []
    for i, item in enumerate(data[:max_count]):
        if not isinstance(item, dict):
            continue
        topic = item.get("topic", "")
        if not topic:
            continue
        raw_resources = item.get("resources") or []
        resources = _normalize_resources(raw_resources)
        priority = str(item.get("priority", "medium")).lower().strip()
        if priority not in _VALID_PRIORITIES:
            priority = "medium"
        related_gaps = _validate_related_gaps(
            item.get("related_gaps") or [], gap_names
        )
        step = int(item.get("step", i + 1))
        depends_on = [
            str(d).strip()
            for d in (item.get("depends_on") or [])
            if isinstance(d, str) and d.strip()
        ]
        results.append(Recommendation(
            topic=topic,
            reason=item.get("reason", ""),
            resources=resources,
            expected_benefit=item.get("expected_benefit", ""),
            priority=priority,
            related_gaps=related_gaps,
            step=step,
            depends_on=depends_on,
        ))
    return results


def _validate_related_gaps(
    raw_gaps: list,
    known_gaps: set[str] | None,
) -> list[str]:
    """Filter related_gaps to only include gaps that exist in the profile."""
    if not raw_gaps:
        return []
    gaps = [str(g).strip() for g in raw_gaps if isinstance(g, str) and g.strip()]
    if known_gaps is None:
        return gaps
    return [g for g in gaps if g in known_gaps]


def parse_resource(raw: str) -> Resource:
    """Parse a raw resource string into a Resource object."""
    raw = raw.strip()
    url_match = re.search(r"https?://\S+", raw)
    if url_match:
        url = url_match.group(0)
        title = raw[:url_match.start()] + raw[url_match.end():]
        title = re.sub(r"\s*[-—–：:]+\s*$", "", title.strip())
        title = re.sub(r"^\s*[-—–：:]+\s*", "", title.strip())
        if not title:
            title = url
        return Resource(title=title, url=url)
    return Resource(title=raw)


def _extract_json_fragment(text: str) -> list | dict | None:
    for open_ch, close_ch in ("[", "]"), ("{", "}"):
        start = text.find(open_ch)
        end = text.rfind(close_ch) + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                continue
    return None


def _normalize_resources(raw: list) -> list[str]:
    resources: list[str] = []
    for r in raw:
        if isinstance(r, str):
            stripped = r.strip()
            if stripped:
                resources.append(stripped)
        elif isinstance(r, dict):
            title = str(r.get("title", "")).strip()
            url = str(r.get("url", "")).strip()
            if title and url:
                resources.append(f"{title} — {url}")
            elif title:
                resources.append(title)
            elif url:
                resources.append(url)
    return resources
