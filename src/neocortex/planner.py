"""Learning plan generator — creates structured weekly plans based on profile and recommendations."""

from __future__ import annotations

import json

from neocortex.llm.base import LLMProvider
from neocortex.models import Language, Profile
from neocortex.recommender import generate_recommendations

_PROMPT_ZH = """你是一位资深技术导师。请根据以下开发者画像和学习推荐，生成一份 {weeks} 周的结构化学习计划。

开发者画像：
{profile_json}

学习推荐（按优先级排序）：
{recommendations_json}

要求：
1. 按推荐的 priority 排序分配到各周（high 优先安排在前面的周）
2. 每周 3-5 个具体的 TODO 项，用 Markdown checkbox 格式（`- [ ]`）
3. 每周末安排一个小型验证任务——在开发者自己的项目中实际应用所学
4. 最后一周（第 {weeks} 周）固定为"回顾与实践"，内容包括：
   - 在自己项目中综合应用前几周所学
   - 重新扫描项目对比成长
   - 总结学习收获
5. 引用开发者画像中的真实项目名称
6. 每周包含：标题、TODO 列表、推荐资源（来自推荐）、预期成果
7. 输出格式为 Markdown，以 `# 个性化学习计划` 开头
8. 在开头加一行：`> 生成日期：{{date}} | 基于你的技能画像`（保留 {{date}} 占位符，不要替换）
9. 加一个 `## 目标` 章节，简述整体学习目标（结合 learning_goal）

用中文输出。"""

_PROMPT_EN = """You are a senior technical mentor. Based on the developer profile and learning recommendations below, generate a structured {weeks}-week learning plan.

Developer profile:
{profile_json}

Learning recommendations (sorted by priority):
{recommendations_json}

Requirements:
1. Arrange topics by recommendation priority (high priority topics go in earlier weeks)
2. Each week should have 3-5 specific TODO items in Markdown checkbox format (`- [ ]`)
3. End each week with a small validation task — applying what was learned in the developer's own projects
4. The final week (Week {weeks}) is always "Review & Practice", including:
   - Applying learnings from previous weeks in own projects
   - Re-scanning projects to compare growth
   - Summarizing learning outcomes
5. Reference actual project names from the developer's profile
6. Each week includes: title, TODO list, recommended resources (from recommendations), expected outcome
7. Output format is Markdown, starting with `# Personalized Learning Plan`
8. Add a line at the top: `> Generated: {{date}} | Based on your skill profile` (keep the {{date}} placeholder, do not replace it)
9. Add a `## Goal` section briefly describing the overall learning objective (aligned with learning_goal)

Output in English."""


async def generate_plan(
    profile: Profile,
    provider: LLMProvider,
    weeks: int = 4,
    language: Language = Language.EN,
) -> str:
    """Generate a structured learning plan and return a Markdown string."""
    recommendations = await generate_recommendations(
        profile, provider, count=weeks * 2, language=language,
    )

    priority_order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda r: priority_order.get(r.priority, 1))

    profile_json = json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2)
    recommendations_json = json.dumps(
        [r.model_dump(mode="json") for r in recommendations],
        ensure_ascii=False,
        indent=2,
    )

    template = _PROMPT_ZH if language == Language.ZH else _PROMPT_EN
    prompt = template.format(
        weeks=weeks,
        profile_json=profile_json,
        recommendations_json=recommendations_json,
    )

    system_msg = (
        "You are a technical learning plan designer. "
        "Output only valid Markdown. Do not wrap in code fences."
    )
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt},
    ]

    response = await provider.chat(messages, json_mode=False)
    return _clean_markdown(response)


def _clean_markdown(text: str) -> str:
    """Strip code fences if the LLM wraps the Markdown output."""
    if not text:
        return text
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[start:end]).strip()
    return text
