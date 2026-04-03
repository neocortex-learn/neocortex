"""Research engine — search the web for articles related to knowledge gaps."""

from __future__ import annotations

import json
from dataclasses import dataclass

from neocortex.llm.base import LLMProvider
from neocortex.models import Language, Profile


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


def web_search(query: str, max_results: int = 10) -> list[SearchResult]:
    """Search the web via DuckDuckGo. No API key required."""
    from ddgs import DDGS

    results: list[SearchResult] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    snippet=r.get("body", ""),
                ))
    except Exception:
        pass
    return results


async def analyze_gaps_for_query(
    topic: str,
    profile: Profile,
    provider: LLMProvider,
    language: Language = Language.EN,
) -> list[str]:
    """Let LLM generate search queries based on the topic and user's knowledge gaps."""
    from neocortex.feeder import _collect_gaps

    gaps = _collect_gaps(profile)
    existing_concepts = _get_existing_concepts()

    lang_inst = "用中文输出。" if language == Language.ZH else "Output in English."

    messages = [
        {
            "role": "system",
            "content": (
                "You generate web search queries for a developer who wants to learn about a topic. "
                "Return a JSON array of 3-5 search query strings. "
                "Each query should target a specific subtopic or angle that the user hasn't covered yet. "
                "Queries should be specific enough to find high-quality technical articles. "
                "Return ONLY a JSON array of strings."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Topic: {topic}\n"
                f"User's skill gaps: {', '.join(gaps[:20]) if gaps else 'None'}\n"
                f"Concepts already in knowledge base: {', '.join(existing_concepts[:20]) if existing_concepts else 'None'}\n"
                f"{lang_inst}"
            ),
        },
    ]

    try:
        raw = await provider.chat(messages, json_mode=True)
        raw = raw.strip()
        if raw.startswith("```"):
            import re
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(q).strip() for q in data if isinstance(q, str) and q.strip()][:5]
    except (json.JSONDecodeError, Exception):
        pass
    return [topic]


async def rank_results(
    results: list[SearchResult],
    topic: str,
    profile: Profile,
    provider: LLMProvider,
    language: Language = Language.EN,
    max_results: int = 5,
) -> list[SearchResult]:
    """Let LLM pick the most relevant search results for the user's gaps."""
    if not results:
        return []

    from neocortex.feeder import _collect_gaps

    gaps = _collect_gaps(profile)

    article_list = "\n".join(
        f"{i}. {r.title} — {r.snippet[:120]}"
        for i, r in enumerate(results)
    )

    messages = [
        {
            "role": "user",
            "content": (
                f"Topic: {topic}\n"
                f"User's skill gaps: {', '.join(gaps[:20]) if gaps else 'general learning'}\n\n"
                f"Search results:\n{article_list}\n\n"
                f"Return a JSON array of indices (0-based) for the {max_results} most relevant, "
                f"high-quality articles. Prefer technical articles, official docs, and well-known "
                f"blogs. Avoid listicles, paywalled content, and low-quality SEO pages. "
                f"Return ONLY a JSON array of integers."
            ),
        },
    ]

    try:
        raw = await provider.chat(messages, json_mode=True)
        indices = json.loads(raw.strip())
        if not isinstance(indices, list):
            return results[:max_results]
        ranked = []
        for idx in indices:
            if isinstance(idx, int) and 0 <= idx < len(results):
                ranked.append(results[idx])
        return ranked[:max_results] if ranked else results[:max_results]
    except (json.JSONDecodeError, Exception):
        return results[:max_results]


def _get_existing_concepts() -> list[str]:
    """Get concept names from knowledge base."""
    try:
        from neocortex.compiler import collect_all_concepts
        from neocortex.config import get_notes_dir

        concepts_dir = get_notes_dir() / "concepts"
        concepts = collect_all_concepts(concepts_dir)
        return [c.name for c in concepts]
    except Exception:
        return []
