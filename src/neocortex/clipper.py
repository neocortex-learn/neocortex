"""Clip processing engine — lightweight LLM processing for fragments."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from neocortex.llm.base import LLMProvider
    from neocortex.models import Language, Profile


async def fetch_clip_content(source: str) -> dict:
    """Fetch content from URL or treat as raw text.

    Returns: {title, content, clip_type, source}
    """
    if not source.startswith(("http://", "https://")):
        return {
            "title": "",
            "content": source,
            "clip_type": "thought",
            "source": "manual",
        }

    import httpx
    from markdownify import markdownify as md
    from readability import Document as ReadabilityDoc

    lower = source.lower()
    is_tweet = "x.com/" in lower or "twitter.com/" in lower
    is_weibo = "weibo.cn/" in lower or "weibo.com/" in lower

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(source, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            html = resp.text
    except (httpx.HTTPError, OSError):
        return {
            "title": source,
            "content": source,
            "clip_type": "bookmark",
            "source": source,
        }

    if is_tweet or is_weibo:
        doc = ReadabilityDoc(html)
        title = doc.short_title() or source
        text = md(doc.summary(), strip=["img", "a"]).strip()
        return {
            "title": title,
            "content": text[:2000] if text else source,
            "clip_type": "tweet",
            "source": source,
        }

    doc = ReadabilityDoc(html)
    title = doc.short_title() or source
    text = md(doc.summary(), strip=["img"]).strip()
    return {
        "title": title,
        "content": text[:2000] if text else source,
        "clip_type": "bookmark",
        "source": source,
    }


def _get_concepts(notes_dir: Path) -> list[str]:
    """Get existing concept names from the concepts/ directory."""
    concepts_dir = notes_dir / "concepts"
    if not concepts_dir.exists():
        return []
    return [f.stem for f in sorted(concepts_dir.glob("*.md"))]


async def process_clip(
    content: str,
    title: str,
    profile: Profile,
    provider: LLMProvider,
    language: Language,
    notes_dir: Path | None = None,
) -> dict:
    """Lightweight LLM processing: summarize, relate, classify.

    1 LLM call, returns:
    {summary, relevance, related_concepts, auto_tags, topic}
    """
    domains = list(profile.skills.domains.keys())
    gaps: list[str] = []
    for d in profile.skills.domains.values():
        gaps.extend(d.gaps)
    for i in profile.skills.integrations.values():
        gaps.extend(i.gaps)
    gaps = list(dict.fromkeys(gaps))

    concepts = _get_concepts(notes_dir) if notes_dir else []

    lang_hint = "用中文回答" if language.value == "zh" else "Answer in English"
    domains_str = ", ".join(domains) if domains else "general"
    gaps_str = ", ".join(gaps[:20]) if gaps else "(none)"
    concepts_str = ", ".join(concepts[:30]) if concepts else "(none)"

    prompt = (
        "You are a knowledge management assistant. The user just clipped a fragment.\n\n"
        f"User skill domains: {domains_str}\n"
        f"User skill gaps: {gaps_str}\n"
        f"Existing concepts: {concepts_str}\n\n"
        f"Fragment:\n{title}\n{content[:1500]}\n\n"
        "Reply in JSON:\n"
        "{\n"
        '  "summary": "one sentence summarizing what this is about",\n'
        '  "relevance": "one sentence on what this means for the user given their profile",\n'
        '  "related_concepts": ["concept1", "concept2"],\n'
        '  "auto_tags": ["tag1", "tag2", "tag3"],\n'
        '  "topic": "best matching domain from the user\'s domain list, or general"\n'
        "}\n\n"
        f"{lang_hint}."
    )

    try:
        raw = await provider.chat(
            [{"role": "user", "content": prompt}],
            json_mode=True,
        )
        raw = raw.strip()
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
        else:
            data = json.loads(raw)
        return {
            "summary": data.get("summary", ""),
            "relevance": data.get("relevance", ""),
            "related_concepts": data.get("related_concepts", [])[:3],
            "auto_tags": data.get("auto_tags", [])[:5],
            "topic": data.get("topic", "general"),
        }
    except Exception:
        return _fallback_process(content, title, domains)


def _fallback_process(content: str, title: str, domains: list[str]) -> dict:
    """Fallback when LLM is unavailable: extract keywords, guess topic."""
    words = re.findall(r"[a-zA-Z\u4e00-\u9fff]{2,}", (title + " " + content)[:500])
    word_freq: dict[str, int] = {}
    for w in words:
        lower = w.lower()
        word_freq[lower] = word_freq.get(lower, 0) + 1
    sorted_words = sorted(word_freq.items(), key=lambda x: -x[1])
    tags = [w for w, _ in sorted_words[:5] if len(w) > 2]

    topic = "general"
    content_lower = (title + " " + content).lower()
    for d in domains:
        if d.lower() in content_lower:
            topic = d
            break

    return {
        "summary": "",
        "relevance": "",
        "related_concepts": [],
        "auto_tags": tags,
        "topic": topic,
    }
