"""Site explorer — scan an author's articles and rank by relevance."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx

from neocortex.llm.base import LLMProvider
from neocortex.models import Language, Profile


@dataclass
class ArticleEntry:
    title: str
    url: str
    snippet: str = ""


_SKIP_EXTENSIONS = frozenset((
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".ico", ".xml", ".json", ".zip", ".pdf", ".woff", ".woff2",
    ".ttf", ".eot", ".mp3", ".mp4", ".webp", ".avif",
))


async def extract_article_links(page_url: str) -> list[ArticleEntry]:
    """Fetch an archive/blog page and extract article links."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.get(page_url)
        resp.raise_for_status()

    html = resp.text
    base_domain = urlparse(page_url).netloc
    current_path = urlparse(page_url).path

    link_pattern = re.compile(
        r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )

    seen_urls: set[str] = set()
    articles: list[ArticleEntry] = []

    for href, text in link_pattern.findall(html):
        if href.startswith("javascript:") or (href.startswith("#") and "/" not in href):
            continue

        full_url = urljoin(page_url, href)
        parsed = urlparse(full_url)

        if parsed.netloc != base_domain:
            continue
        if parsed.path == current_path:
            continue
        if any(full_url.lower().endswith(ext) for ext in _SKIP_EXTENSIONS):
            continue

        canonical = parsed._replace(fragment="").geturl()
        if canonical in seen_urls:
            continue
        seen_urls.add(canonical)

        clean_title = re.sub(r"<[^>]+>", "", text).strip()
        if not clean_title or len(clean_title) < 3:
            continue

        articles.append(ArticleEntry(title=clean_title, url=canonical))

    return articles


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
        "- P2: interesting but doesn't match current learning direction\n\n"
        "Output JSON:\n"
        '{\n'
        '  "author_overview": "one sentence about this author/site\'s theme",\n'
        '  "articles": [\n'
        '    {"index": 0, "priority": "P0", "reason": "one sentence"}\n'
        '  ]\n'
        '}\n\n'
        "Every article must appear in the output. "
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

    prompt = _build_prompt(articles, profile, language)

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
            for i, a in enumerate(articles)
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
        if not isinstance(idx, int) or idx < 0 or idx >= len(articles):
            continue
        index_map[idx] = item

    results: list[dict] = []
    for i, a in enumerate(articles):
        llm_item = index_map.get(i, {})
        priority = llm_item.get("priority", "P1")
        if priority not in ("P0", "P1", "P2"):
            priority = "P1"
        results.append({
            "index": i,
            "title": a.title,
            "url": a.url,
            "priority": priority,
            "reason": llm_item.get("reason", ""),
        })

    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    results.sort(key=lambda r: priority_order.get(r["priority"], 1))

    return author_overview, results
