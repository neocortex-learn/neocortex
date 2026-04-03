"""Feed engine — fetch RSS feeds and filter by skill gaps."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import feedparser
import httpx

from neocortex.llm.base import LLMProvider
from neocortex.models import Language, Profile


@dataclass
class FeedItem:
    title: str
    url: str
    feed_name: str
    published: str
    summary: str


async def fetch_feeds(
    feeds: list[dict],
    history: dict[str, str],
) -> tuple[list[FeedItem], dict[str, str]]:
    """Fetch all configured feeds and return new items.

    Returns (new_items, updated_history).
    """
    if not feeds:
        return [], history

    updated_history = dict(history)

    async def _fetch_one(feed: dict) -> list[FeedItem]:
        url = feed["url"]
        name = feed.get("name", url)
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except (httpx.HTTPError, OSError):
            return []

        parsed = feedparser.parse(resp.text)
        if not parsed.entries:
            return []

        last_seen = history.get(url)
        items: list[FeedItem] = []

        for entry in parsed.entries:
            entry_id = entry.get("id") or entry.get("link", "")
            if last_seen and entry_id == last_seen:
                break

            link = entry.get("link", "")
            title = entry.get("title", "")
            published = ""
            if hasattr(entry, "published"):
                published = entry.published
            elif hasattr(entry, "updated"):
                published = entry.updated

            summary = ""
            if hasattr(entry, "summary"):
                summary = entry.summary
                if len(summary) > 300:
                    summary = summary[:300] + "..."

            if title and link:
                items.append(FeedItem(
                    title=title,
                    url=link,
                    feed_name=name,
                    published=published,
                    summary=summary,
                ))

        if parsed.entries:
            first_id = parsed.entries[0].get("id") or parsed.entries[0].get("link", "")
            if first_id:
                updated_history[url] = first_id

        return items

    results = await asyncio.gather(*[_fetch_one(f) for f in feeds], return_exceptions=True)

    all_items: list[FeedItem] = []
    for result in results:
        if isinstance(result, list):
            all_items.extend(result)

    return all_items, updated_history


async def filter_by_gaps(
    items: list[FeedItem],
    profile: Profile,
    provider: LLMProvider | None,
    language: Language,
    max_results: int = 10,
) -> list[FeedItem]:
    """Filter feed items by relevance to user's skill gaps."""
    if not items:
        return []

    gaps = _collect_gaps(profile)
    if not gaps:
        return items[:max_results]

    if provider is None:
        return _keyword_fallback(items, gaps, max_results)

    return await _llm_filter(items, gaps, provider, language, max_results)


def _collect_gaps(profile: Profile) -> list[str]:
    """Extract all gap names from the profile."""
    gaps: list[str] = []
    for domain in profile.skills.domains.values():
        gaps.extend(domain.gaps)
    for integration in profile.skills.integrations.values():
        gaps.extend(integration.gaps)
    return list(set(gaps))


def _keyword_fallback(
    items: list[FeedItem],
    gaps: list[str],
    max_results: int,
) -> list[FeedItem]:
    """Simple keyword matching when no LLM is available."""
    gap_words: set[str] = set()
    for gap in gaps:
        for word in gap.lower().replace("-", " ").replace("_", " ").split():
            if len(word) >= 3:
                gap_words.add(word)

    if not gap_words:
        return items[:max_results]

    scored: list[tuple[int, FeedItem]] = []
    for item in items:
        text = f"{item.title} {item.summary}".lower()
        score = sum(1 for w in gap_words if w in text)
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:max_results]]


async def _llm_filter(
    items: list[FeedItem],
    gaps: list[str],
    provider: LLMProvider,
    language: Language,
    max_results: int,
) -> list[FeedItem]:
    """Use LLM to filter articles by gap relevance."""
    article_list = "\n".join(
        f"{i}. {item.title} — {item.summary[:100]}"
        for i, item in enumerate(items)
    )

    gaps_text = ", ".join(gaps[:30])

    prompt = (
        f"The user has these skill gaps: {gaps_text}\n\n"
        f"Here are new articles:\n{article_list}\n\n"
        f"Return a JSON array of indices (0-based) for articles most relevant "
        f"to the user's skill gaps. Max {max_results} results. "
        f"Only include articles that would help fill at least one gap. "
        f"Return ONLY a JSON array of integers, e.g. [0, 3, 5]."
    )

    try:
        response = await provider.chat(
            [{"role": "user", "content": prompt}],
            json_mode=True,
        )
        text = response.strip()
        if text.startswith("{"):
            data = json.loads(text)
            indices = data.get("indices", data.get("results", []))
        else:
            indices = json.loads(text)

        if not isinstance(indices, list):
            return _keyword_fallback(items, gaps, max_results)

        filtered = []
        for idx in indices:
            if isinstance(idx, int) and 0 <= idx < len(items):
                filtered.append(items[idx])

        return filtered[:max_results] if filtered else _keyword_fallback(items, gaps, max_results)
    except (json.JSONDecodeError, Exception):
        return _keyword_fallback(items, gaps, max_results)
