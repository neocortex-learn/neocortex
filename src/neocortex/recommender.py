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
        lines = [f"- {g['gap']} ({g['domain']}, {g['level']})" for g in gaps]
        sections.append("## Skill gaps\n" + "\n".join(lines))

    if records:
        completed = [r for r in records if r.status == "completed"][-10:]
        if completed:
            lines = [f"- {r.topic}" for r in completed]
            sections.append("## Recently completed\n" + "\n".join(lines))

    topics_read = profile.learning_history.topics_read[-10:]
    if topics_read:
        lines = [f"- {t.title} ({t.source})" for t in topics_read]
        sections.append("## Recently read\n" + "\n".join(lines))

    return "\n\n".join(sections)


_PROMPT_ZH = """你是一个资深技术导师。根据以下开发者画像，推荐 {count} 个最值得学习的主题。

{context}

推荐原则：
1. 优先补盲区（gaps）——这些是已有技能中缺失的关键知识
2. 结合学习目标（learning_goal）——推荐方向要与目标一致
3. 考虑已完成和已读内容——不要推荐已经在学的
4. 投入产出比——优先推荐能快速提升且对现有项目有直接帮助的
5. 难度匹配——基于当前水平推荐 +1~+2 级别的内容，不要跳太远

对每个推荐，提供：
- topic: 具体的学习主题（不要太宽泛，如"Redis Cluster 配置与运维"而不是"Redis"）
- reason: 为什么要学（结合画像中的具体项目和技能说明）
- resources: 2-3 个推荐的学习资源（每个资源为 {{"title": "...", "url": "...", "type": "article"}} 格式）
- expected_benefit: 学完后能获得什么（具体到项目层面）
- priority: high / medium / low
- related_gaps: 这个推荐对应的 gap 名称列表（必须来自上面的 Skill gaps 列表）

用中文回答。输出 JSON 数组格式。"""

_PROMPT_EN = """You are a senior technical mentor. Based on the developer profile below, recommend {count} topics most worth learning.

{context}

Principles:
1. Prioritize filling gaps — these are missing critical knowledge in existing skills
2. Align with learning_goal
3. Consider completed and recently read content — don't recommend what's already being studied
4. ROI — prioritize topics that quickly improve and directly help existing projects
5. Difficulty match — recommend +1~+2 levels above current, don't jump too far

For each recommendation, provide:
- topic: specific learning topic (e.g. "Redis Cluster setup & operations" not just "Redis")
- reason: why learn this (reference specific projects and skills from the profile)
- resources: 2-3 recommended resources (each as {{"title": "...", "url": "...", "type": "article"}})
- expected_benefit: what you gain after learning (specific to project level)
- priority: high / medium / low
- related_gaps: list of gap names this recommendation addresses (must come from the Skill gaps list above)

Output as a JSON array."""


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
    for item in data[:max_count]:
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
        results.append(Recommendation(
            topic=topic,
            reason=item.get("reason", ""),
            resources=resources,
            expected_benefit=item.get("expected_benefit", ""),
            priority=priority,
            related_gaps=related_gaps,
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
