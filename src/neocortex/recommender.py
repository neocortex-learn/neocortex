"""Learning path recommender — suggests what to learn next based on your profile."""

from __future__ import annotations

import json

from neocortex.llm.base import LLMProvider
from neocortex.models import Profile, Recommendation


async def generate_recommendations(
    profile: Profile,
    provider: LLMProvider,
    count: int = 5,
) -> list[Recommendation]:
    profile_json = json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2)

    prompt = f"""你是一个资深技术导师。根据以下开发者画像，推荐 {count} 个最值得学习的主题。

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

输出 JSON 数组格式。"""

    messages = [
        {"role": "system", "content": "You are a technical learning advisor. Always respond in valid JSON only."},
        {"role": "user", "content": prompt},
    ]

    response = await provider.chat(messages, json_mode=False)

    return _parse_recommendations(response, count)


def _parse_recommendations(text: str, max_count: int) -> list[Recommendation]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1 if lines[0].strip().startswith("```") else 0
        end = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[start:end])

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
            except json.JSONDecodeError:
                return []
        else:
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
        raw_resources = item.get("resources", [])
        resources = []
        for r in raw_resources:
            if isinstance(r, str):
                resources.append(r)
            elif isinstance(r, dict):
                title = r.get("title", "")
                url = r.get("url", "")
                resources.append(f"{title} — {url}" if title and url else title or url)
        results.append(Recommendation(
            topic=item.get("topic", ""),
            reason=item.get("reason", ""),
            resources=resources,
            expected_benefit=item.get("expected_benefit", ""),
            priority=item.get("priority", "medium"),
        ))
    return results
