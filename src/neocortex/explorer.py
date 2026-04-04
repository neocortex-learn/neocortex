"""Site explorer — scan an author's articles and rank by relevance."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from neocortex.llm.base import LLMProvider
from neocortex.models import Language, Profile


@dataclass
class ArticleEntry:
    title: str
    url: str
    snippet: str = ""





async def extract_article_links(page_url: str) -> list[ArticleEntry]:
    """Fetch an RSS/Atom feed and extract article entries.

    If the URL is an HTML page, tries to discover a feed link in <head>.
    """
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.get(page_url)
        resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    text = resp.text

    if _is_feed_content(content_type, text):
        return _parse_feed(text)

    # HTML 页面：尝试发现 feed 链接
    feed_url = _discover_feed_url(text, page_url)
    if feed_url:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            feed_resp = await client.get(feed_url)
            feed_resp.raise_for_status()
        return _parse_feed(feed_resp.text)

    return []


def _is_feed_content(content_type: str, text: str) -> bool:
    """Check if content is RSS/Atom feed."""
    if "xml" in content_type or "rss" in content_type or "atom" in content_type:
        return True
    stripped = text.strip()[:200]
    return "<rss" in stripped or "<feed" in stripped or "<?xml" in stripped


def _parse_feed(text: str) -> list[ArticleEntry]:
    """Parse RSS/Atom feed into article entries."""
    import feedparser

    parsed = feedparser.parse(text)
    articles: list[ArticleEntry] = []
    seen: set[str] = set()

    for entry in parsed.entries:
        link = entry.get("link", "")
        title = entry.get("title", "")
        if not title or not link or link in seen:
            continue
        seen.add(link)

        snippet = ""
        if hasattr(entry, "summary"):
            snippet = re.sub(r"<[^>]+>", "", entry.summary).strip()[:200]

        articles.append(ArticleEntry(title=title, url=link, snippet=snippet))

    return articles


def _discover_feed_url(html: str, page_url: str) -> str | None:
    """Try to find RSS/Atom feed link in HTML <head>."""
    # <link rel="alternate" type="application/rss+xml" href="...">
    feed_pattern = re.compile(
        r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*href=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    match = feed_pattern.search(html)
    if match:
        return urljoin(page_url, match.group(1))

    # 反过来的属性顺序
    feed_pattern2 = re.compile(
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]*type=["\']application/(?:rss|atom)\+xml["\']',
        re.IGNORECASE,
    )
    match2 = feed_pattern2.search(html)
    if match2:
        return urljoin(page_url, match2.group(1))

    return None




def _collect_gaps(profile: Profile) -> list[str]:
    gaps: list[str] = []
    seen: set[str] = set()
    for domain in profile.skills.domains.values():
        for g in domain.gaps:
            if g not in seen:
                gaps.append(g)
                seen.add(g)
    for integration in profile.skills.integrations.values():
        for g in integration.gaps:
            if g not in seen:
                gaps.append(g)
                seen.add(g)
    return gaps


def _build_prompt(
    articles: list[ArticleEntry],
    profile: Profile,
    language: Language,
) -> str:
    domains = list(profile.skills.domains.keys())
    gaps = _collect_gaps(profile)
    goal = ""
    if profile.persona and profile.persona.learning_goal:
        goal = profile.persona.learning_goal.value

    article_list = "\n".join(
        f"{i}. {a.title}" for i, a in enumerate(articles)
    )

    lang_instruction = "回复使用中文。" if language == Language.ZH else ""

    return (
        "You are a learning advisor. The user found a promising author/site and wants to "
        "know which articles are worth reading.\n\n"
        f"User skill domains: {', '.join(domains) if domains else '(none yet)'}\n"
        f"User skill gaps: {', '.join(gaps) if gaps else '(none yet)'}\n"
        f"User learning goal: {goal or '(not set)'}\n\n"
        f"Articles on this page:\n{article_list}\n\n"
        "Rate each article:\n"
        "- P0: directly fills an active gap — must read\n"
        "- P1: relevant but not urgent\n"
        "- P2: interesting but doesn't match current learning direction\n"
        "- Also give each article a relevance score (1-10, 10 = most relevant to user's gaps)\n\n"
        "Output JSON:\n"
        '{\n'
        '  "author_overview": "one sentence about this author/site\'s theme",\n'
        '  "articles": [\n'
        '    {"index": 0, "priority": "P0", "score": 9, "reason": "one sentence"}\n'
        '  ]\n'
        '}\n\n'
        "Every article must appear in the output. Sort by score descending (most relevant first). "
        + lang_instruction
    )


async def batch_scan_articles(
    articles: list[ArticleEntry],
    profile: Profile,
    provider: LLMProvider,
    language: Language = Language.EN,
) -> tuple[str, list[dict]]:
    """Batch scan articles: rank by gap relevance.

    Returns (author_overview, sorted_results).
    Each result: {index, title, url, priority, reason}.
    """
    if not articles:
        return "", []

    # 文章太多时截断，避免超出 LLM 上下文
    max_articles = 50
    truncated = len(articles) > max_articles
    scan_articles = articles[:max_articles]

    prompt = _build_prompt(scan_articles, profile, language)

    try:
        raw = await provider.chat(
            [{"role": "user", "content": prompt}],
            json_mode=True,
        )
        data = json.loads(raw)
    except Exception:
        results = [
            {
                "index": i,
                "title": a.title,
                "url": a.url,
                "priority": "P1",
                "reason": "",
            }
            for i, a in enumerate(scan_articles)
        ]
        return "", results

    author_overview = data.get("author_overview", "") if isinstance(data, dict) else ""
    raw_articles = data.get("articles", []) if isinstance(data, dict) else []

    index_map: dict[int, dict] = {}
    for item in raw_articles:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        if idx is None:
            continue
        if isinstance(idx, str) and idx.isdigit():
            idx = int(idx)
        if not isinstance(idx, int) or idx < 0 or idx >= len(scan_articles):
            continue
        index_map[idx] = item

    results: list[dict] = []
    for i, a in enumerate(scan_articles):
        llm_item = index_map.get(i, {})
        priority = llm_item.get("priority", "P1")
        if priority not in ("P0", "P1", "P2"):
            priority = "P1"
        score = llm_item.get("score", 5)
        if not isinstance(score, (int, float)):
            score = 5
        results.append({
            "index": i,
            "title": a.title,
            "url": a.url,
            "priority": priority,
            "score": score,
            "reason": llm_item.get("reason", ""),
        })

    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    results.sort(key=lambda r: (priority_order.get(r["priority"], 1), -r["score"]))

    return author_overview, results
