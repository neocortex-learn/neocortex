"""Learning path recommender — suggests what to learn next based on your profile."""

from __future__ import annotations

import json

from neocortex.llm.base import LLMProvider
from neocortex.models import Language, Profile, Recommendation

_PROMPT_ZH = """你是一个资深技术导师。根据以下开发者画像，推荐 {count} 个最值得学习的主题。

开发者画像：
{profile_json}

推荐原则：
1. 优先补盲区（gaps）——这些是已有技能中缺失的关键知识
2. 结合学习目标（learning_goal）——推荐方向要与目标一致
3. 考虑学习历史（learning_history）——不要推荐已经在学的
4. 投入产出比——优先推荐能快速提升且对现有项目有直接帮助的
5. 难度匹配——基于当前水平推荐 +1~+2 级别的内容，不要跳太远

对每个推荐，提供：
- topic: 具体的学习主题（不要太宽泛，如"Redis Cluster 配置与运维"而不是"Redis"）
- reason: 为什么要学（结合画像中的具体项目和技能说明）
- resources: 2-3 个推荐的学习资源（书籍章节、官方文档 URL、优质文章）
- expected_benefit: 学完后能获得什么（具体到项目层面）
- priority: high / medium / low

用中文回答。输出 JSON 数组格式。"""

_PROMPT_EN = """You are a senior technical mentor. Based on the developer profile below, recommend {count} topics most worth learning.

Developer profile:
{profile_json}

Principles:
1. Prioritize filling gaps — these are missing critical knowledge in existing skills
2. Align with learning_goal
3. Consider learning_history — don't recommend what's already being studied
4. ROI — prioritize topics that quickly improve and directly help existing projects
5. Difficulty match — recommend +1~+2 levels above current, don't jump too far

For each recommendation, provide:
- topic: specific learning topic (e.g. "Redis Cluster setup & operations" not just "Redis")
- reason: why learn this (reference specific projects and skills from the profile)
- resources: 2-3 recommended resources (book chapters, official doc URLs, quality articles)
- expected_benefit: what you gain after learning (specific to project level)
- priority: high / medium / low

Output as a JSON array."""


async def generate_recommendations(
    profile: Profile,
    provider: LLMProvider,
    count: int = 5,
    language: Language = Language.EN,
) -> list[Recommendation]:
    profile_json = json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2)

    template = _PROMPT_ZH if language == Language.ZH else _PROMPT_EN
    prompt = template.format(count=count, profile_json=profile_json)

    system_msg = "You are a technical learning advisor. Always respond in valid JSON only."
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt},
    ]

    response = await provider.chat(messages, json_mode=False)

    return _parse_recommendations(response, count)


_VALID_PRIORITIES = {"high", "medium", "low"}


def _parse_recommendations(text: str, max_count: int) -> list[Recommendation]:
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
        results.append(Recommendation(
            topic=topic,
            reason=item.get("reason", ""),
            resources=resources,
            expected_benefit=item.get("expected_benefit", ""),
            priority=priority,
        ))
    return results


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
