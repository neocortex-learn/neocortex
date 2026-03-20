"""LLM-powered insight extractor for chat history messages."""

from __future__ import annotations

import json
from datetime import date

from neocortex.importer.chatgpt import ParsedMessage
from neocortex.llm.base import LLMProvider
from neocortex.models import ChatInsights, QuestionAsked

EXTRACTION_PROMPT = """\
你是一个开发者能力分析专家。以下是一个开发者与 AI 助手的对话历史（仅用户侧消息）。

请分析这些对话，提取以下信息：

1. questions_asked: 用户提出的技术问题，标注主题和难度级别
   - topic: 技术主题（如 redis, fastapi, react, sql）
   - level: 问题体现的水平（beginner/intermediate/advanced）
   - date: 大致日期
   - summary: 问题摘要

2. topics_discussed: 用户讨论过的技术领域（字符串列表）

3. confusion_points: 用户明确表示困惑或反复追问的点（字符串列表）

4. growth_trajectory: 从对话时间线推断的学习方向
   （例：从前端问题逐渐转向系统设计）

只提取与技术学习相关的内容，忽略闲聊。
输出 JSON 格式，结构如下：
{
  "questions_asked": [{"topic": "", "level": "", "date": "", "summary": ""}],
  "topics_discussed": [],
  "confusion_points": [],
  "growth_trajectory": ""
}

用户消息：
"""


def _format_messages_for_prompt(messages: list[ParsedMessage]) -> str:
    lines: list[str] = []
    for msg in messages:
        lines.append(f"[{msg.conversation_title}] {msg.content}")
    return "\n".join(lines)


def _parse_llm_json(raw: str) -> dict:
    """Best-effort parse of LLM JSON response, stripping markdown fences."""
    text = raw.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())


def _merge_batch_results(results: list[dict]) -> dict:
    all_questions: list[dict] = []
    all_topics: set[str] = set()
    all_confusion: set[str] = set()
    growth = ""

    for r in results:
        all_questions.extend(r.get("questions_asked", []))
        all_topics.update(r.get("topics_discussed", []))
        all_confusion.update(r.get("confusion_points", []))
        trajectory = r.get("growth_trajectory", "")
        if trajectory:
            growth = trajectory

    return {
        "questions_asked": all_questions,
        "topics_discussed": sorted(all_topics),
        "confusion_points": sorted(all_confusion),
        "growth_trajectory": growth,
    }


async def extract_insights(
    messages: list[ParsedMessage],
    provider: LLMProvider,
    source: str,
    batch_size: int = 50,
) -> ChatInsights:
    """Batch-send user messages to LLM and extract structured insights.

    1. Sort messages by timestamp.
    2. Split into batches of *batch_size*.
    3. Send each batch to the LLM for analysis.
    4. Merge batch results into a single ChatInsights.
    """
    sorted_messages = sorted(messages, key=lambda m: m.timestamp)

    batches: list[list[ParsedMessage]] = []
    for i in range(0, len(sorted_messages), batch_size):
        batches.append(sorted_messages[i : i + batch_size])

    batch_results: list[dict] = []
    for i, batch in enumerate(batches):
        try:
            prompt_text = EXTRACTION_PROMPT + _format_messages_for_prompt(batch)
            llm_messages = [{"role": "user", "content": prompt_text}]
            raw_response = await provider.chat(llm_messages, json_mode=True)
            parsed = _parse_llm_json(raw_response)
            batch_results.append(parsed)
        except Exception as e:
            import sys
            print(f"Warning: Failed to process batch {i+1}: {e}", file=sys.stderr)
            continue

    merged = _merge_batch_results(batch_results)

    questions = [
        QuestionAsked(
            topic=q.get("topic", ""),
            level=q.get("level", "beginner"),
            date=q.get("date", ""),
            summary=q.get("summary", ""),
        )
        for q in merged["questions_asked"]
    ]

    timestamps = [m.timestamp for m in sorted_messages if m.timestamp > 0]
    date_range: list[str] = []
    if timestamps:
        earliest = date.fromtimestamp(min(timestamps)).isoformat()
        latest = date.fromtimestamp(max(timestamps)).isoformat()
        date_range = [earliest, latest]

    return ChatInsights(
        source=source,
        imported_at=date.today().isoformat(),
        message_count=len(sorted_messages),
        date_range=date_range,
        questions_asked=questions,
        topics_discussed=merged["topics_discussed"],
        confusion_points=merged["confusion_points"],
        growth_trajectory=merged["growth_trajectory"],
    )
