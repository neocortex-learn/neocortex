"""Clip processing engine — lightweight LLM processing for fragments."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from neocortex.llm.base import LLMProvider
    from neocortex.models import Language, Profile


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}


def _sanitize_text(text: str) -> str:
    """Remove characters that break XML/API serialization.

    Strips: C0 control chars (except tab/newline/CR), DEL, C1 control chars (0x7F-0x9F),
    surrogates, and non-characters. These cause errors in Anthropic/OpenAI SDKs.
    """
    def _valid(c: str) -> bool:
        cp = ord(c)
        if cp <= 0x1F:
            return cp in (0x9, 0xA, 0xD)  # tab, newline, carriage return
        if 0x7F <= cp <= 0x9F:
            return False  # DEL + C1 control characters
        if 0xD800 <= cp <= 0xDFFF:
            return False  # surrogates
        if cp in (0xFFFE, 0xFFFF):
            return False  # non-characters
        return True
    return "".join(c for c in text if _valid(c))


async def fetch_clip_content(source: str) -> dict:
    """Fetch content from URL, image file, or treat as raw text.

    Returns: {title, content, clip_type, source}
    """
    from pathlib import Path

    # Check if source is a local image file (guard against long text being treated as path)
    if not source.startswith(("http://", "https://")) and len(source) < 500:
        try:
            path = Path(source).expanduser()
            is_image = path.exists() and path.suffix.lower() in _IMAGE_EXTENSIONS
        except OSError:
            is_image = False
        if is_image:
            return {
                "title": path.stem,
                "content": "",  # Will be filled by LLM describe_image in cmd_clip
                "clip_type": "screenshot",
                "source": str(path),
                "_image_path": str(path),
            }
        return {
            "title": "",
            "content": _sanitize_text(source),
            "clip_type": "thought",
            "source": "manual",
        }

    # A real URL is a single line with no whitespace — if it contains newlines,
    # it's pasted text that happens to start with a URL (e.g. Zhihu copy includes URL + article)
    if "\n" in source or "\r" in source:
        return {
            "title": "",
            "content": _sanitize_text(source),
            "clip_type": "thought",
            "source": "manual",
            "_fetch_status": "ok",
            "_fetch_error": None,
        }

    import httpx
    from markdownify import markdownify as md
    from readability import Document as ReadabilityDoc

    lower = source.lower()
    is_tweet = "x.com/" in lower or "twitter.com/" in lower
    is_weibo = "weibo.cn/" in lower or "weibo.com/" in lower
    is_wechat = "mp.weixin.qq.com" in lower

    if is_wechat:
        try:
            result = await _fetch_wechat_clip(source)
            result.setdefault("_fetch_status", "ok")
            result.setdefault("_fetch_error", None)
            return result
        except Exception as exc:
            return _failed_fetch_payload(source, str(exc) or exc.__class__.__name__)

    if is_tweet:
        result = await _fetch_tweet_clip(source)
        if result.get("_fetch_status") == "ok":
            return result
        # fall through to generic httpx as best-effort backup; if that also
        # produces garbage, _check_content_quality below will mark it failed.

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(source, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            html = resp.text
    except (httpx.HTTPError, OSError) as exc:
        return _failed_fetch_payload(source, f"HTTP fetch failed: {exc}")

    if is_tweet or is_weibo:
        doc = ReadabilityDoc(html)
        title = doc.short_title() or source
        text = md(doc.summary(), strip=["img", "a"]).strip()
        payload = {
            "title": title,
            "content": text[:2000] if text else source,
            "clip_type": "tweet",
            "source": source,
        }
        return _annotate_quality(payload, text, source)

    doc = ReadabilityDoc(html)
    title = doc.short_title() or source
    text = md(doc.summary(), strip=["img"]).strip()
    payload = {
        "title": title,
        "content": text[:2000] if text else source,
        "clip_type": "bookmark",
        "source": source,
    }
    return _annotate_quality(payload, text, source)


# ── Fetch quality / failure helpers ──

_FETCH_ERROR_MARKERS = (
    "login required",
    "please enable javascript",
    "javascript is not available",
    "404 not found",
    "page not found",
    "please log in",
    "rate limit exceeded",
    "access denied",
    "请先登录",
    "需要登录",
    "页面不存在",
)


def _failed_fetch_payload(source: str, error: str) -> dict:
    """Build a dict signalling fetch failure — caller must refuse to save."""
    return {
        "title": source,
        "content": "",
        "clip_type": "bookmark",
        "source": source,
        "_fetch_status": "failed",
        "_fetch_error": error,
    }


def _annotate_quality(payload: dict, extracted_text: str, source: str) -> dict:
    """Detect obvious fetch garbage (empty / login wall / error page).

    Source URLs that resolve to less than ~100 chars of real content or that
    contain known error markers are flagged as failed so the caller can
    refuse to save and stop the LLM from hallucinating about an error page.
    """
    payload.setdefault("_fetch_status", "ok")
    payload.setdefault("_fetch_error", None)
    text = (extracted_text or "").strip()
    text_lower = text.lower()
    if not text or len(text) < 100:
        if source.startswith(("http://", "https://")):
            payload["_fetch_status"] = "failed"
            payload["_fetch_error"] = (
                f"extracted content too short ({len(text)} chars) — "
                "likely a login wall / JS-only page / empty article"
            )
        return payload
    for marker in _FETCH_ERROR_MARKERS:
        if marker in text_lower:
            payload["_fetch_status"] = "failed"
            payload["_fetch_error"] = f"page contains error marker: {marker!r}"
            return payload
    return payload


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
            # Status metadata for caller (禁止静默失败 — see CLIENT_PROPOSAL §5.1)
            "_llm_status": "ok",
            "_llm_error": None,
        }
    except Exception as exc:
        fallback = _fallback_process(content, title, domains)
        fallback["_llm_status"] = "failed"
        fallback["_llm_error"] = str(exc) or exc.__class__.__name__
        return fallback


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


def _parse_wechat_output(stdout: str):
    """Extract saved file path from wechat-article-to-markdown stdout."""
    from pathlib import Path
    for line in stdout.splitlines():
        if "已保存:" in line or "已保存：" in line:
            parts = re.split(r"已保存[:：]\s*", line, maxsplit=1)
            if len(parts) == 2:
                candidate = Path(parts[1].strip())
                if candidate.exists():
                    return candidate
    return None


async def _fetch_wechat_clip(source: str) -> dict:
    """Fetch WeChat article content using wechat-article-to-markdown tool."""
    import shutil
    import subprocess
    from pathlib import Path

    if not shutil.which("wechat-article-to-markdown"):
        raise ValueError(
            "WeChat article fetching requires wechat-article-to-markdown. "
            "Install: uv tool install wechat-article-to-markdown"
        )

    result = subprocess.run(
        ["wechat-article-to-markdown", source],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip() if result.stderr else "Unknown error"
        raise ValueError(
            f"WeChat article fetch failed: {error_msg}\n"
            "Try: uv tool install --force wechat-article-to-markdown --with 'httpx[socks]'"
        )

    # Parse saved path from stdout: "✅ 已保存: <path>"
    md_path = _parse_wechat_output(result.stdout)
    if md_path is None:
        raise ValueError(
            "wechat-article-to-markdown produced no output. "
            "The article may be behind a paywall or login wall."
        )

    content = md_path.read_text(encoding="utf-8")
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else source

    return {
        "title": title,
        "content": content[:2000] if content else source,
        "clip_type": "bookmark",
        "source": source,
    }


async def _fetch_tweet_clip(source: str) -> dict:
    """Fetch X/Twitter content via x-tweet-fetcher (zero-deps FxTwitter mode).

    Returns a payload dict with _fetch_status='ok' on success.
    On any failure (tool not installed, subprocess error, empty output)
    returns a failed payload so the caller can fall back to generic httpx.
    """
    import shutil
    import subprocess

    if not shutil.which("x-tweet-fetcher"):
        return _failed_fetch_payload(
            source,
            "x-tweet-fetcher not installed. "
            "Install: uv tool install git+https://github.com/ythx-101/x-tweet-fetcher",
        )

    try:
        result = subprocess.run(
            ["x-tweet-fetcher", "--url", source, "--text-only"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return _failed_fetch_payload(source, "x-tweet-fetcher timed out (>30s)")
    except OSError as exc:
        return _failed_fetch_payload(source, f"x-tweet-fetcher launch failed: {exc}")

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip() or "unknown error"
        return _failed_fetch_payload(source, f"x-tweet-fetcher exit {result.returncode}: {err[:200]}")

    text = (result.stdout or "").strip()
    if not text:
        return _failed_fetch_payload(source, "x-tweet-fetcher produced empty output")

    # First line is usually "@user: <first part>"; use as title fallback
    first_line = text.splitlines()[0].strip() if text else source
    title = first_line[:80] if first_line else source

    return {
        "title": title,
        "content": text[:2000],
        "clip_type": "tweet",
        "source": source,
        "_fetch_status": "ok",
        "_fetch_error": None,
    }
