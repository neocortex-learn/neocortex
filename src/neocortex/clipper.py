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
        body = text[:_MAX_CLIP_CONTENT_CHARS] if text else source
        payload = {
            "title": title,
            "content": _with_source_link(body, source),
            "clip_type": "tweet",
            "source": source,
        }
        return _annotate_quality(payload, text, source)

    doc = ReadabilityDoc(html)
    title = doc.short_title() or source
    text = md(doc.summary(), strip=["img"]).strip()
    body = text[:_MAX_CLIP_CONTENT_CHARS] if text else source
    payload = {
        "title": title,
        "content": _with_source_link(body, source),
        "clip_type": "bookmark",
        "source": source,
    }
    return _annotate_quality(payload, text, source)


# ── Fetch quality / failure helpers ──

# Hard upper bound on saved clip content. The original 2000-char cap (set
# defensively for early CLI experimentation) was silently truncating long
# X Articles / WeChat posts / readability extracts mid-paragraph — users
# would see "only half the tweet was saved". 50KB easily covers any
# tweet, X Article, or WeChat long-form post while still bounding memory
# against runaway readability extracts of giant pages.
_MAX_CLIP_CONTENT_CHARS = 50_000


def _with_source_link(content: str, source: str) -> str:
    """Prepend an inline ``> 原文: <url>`` line so renders / Obsidian show a
    one-click jump back to the source. Frontmatter has ``source:`` too, but
    that's hidden from the rendered view and from most clients.

    No-op for non-URL sources (``manual`` text, image paths). Idempotent —
    if the same line already opens the content, returns content unchanged.
    """
    if not source.startswith(("http://", "https://")):
        return content
    header = f"> 原文：<{source}>"
    if content.lstrip().startswith(header):
        return content
    return f"{header}\n\n{content}" if content else header


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

# Above this many extracted chars, a wall/error marker is treated as incidental
# (a real page that merely *mentions* the phrase, or a third-party widget's
# noscript fallback) rather than a hard fetch failure. Wall pages extract to
# far less than this.
_WALL_TEXT_THRESHOLD = 600


def _failed_fetch_payload(source: str, error: str) -> dict:
    """Build a dict signalling hard fetch failure — caller must refuse to save."""
    return {
        "title": source,
        "content": "",
        "clip_type": "bookmark",
        "source": source,
        "_fetch_status": "failed",
        "_fetch_error": error,
        "_fetch_quality": "none",
    }


def _annotate_quality(payload: dict, extracted_text: str, source: str) -> dict:
    """Classify fetch outcome into three states (P2 fix 2026-05-20):

    - ``_fetch_status='failed'`` — hard error (HTTP error / known error
      markers like login walls / 404 pages). Caller MUST reject.
    - ``_fetch_status='ok'`` + ``_fetch_quality='weak'`` — short / sparse
      extraction (< 100 chars) from a URL, but no error markers. Caller
      should save as bookmark but skip LLM tagging (avoid hallucination
      about near-empty content). Covers real short pages / index pages /
      issue trackers / pure-link bookmark intent.
    - ``_fetch_status='ok'`` + ``_fetch_quality='full'`` — normal content.
    """
    payload.setdefault("_fetch_status", "ok")
    payload.setdefault("_fetch_error", None)
    payload.setdefault("_fetch_quality", "full")

    text = (extracted_text or "").strip()
    text_lower = text.lower()

    # Hard errors first (override quality) — but only when extraction is short.
    # A real wall page (JS wall / login wall / 404) extracts to almost nothing:
    # the marker *is* essentially the whole body. When we've pulled a full
    # article (thousands of chars), a stray marker is incidental noise — e.g. a
    # Disqus comments "<noscript>Please enable JavaScript…</noscript>" fallback
    # tacked onto the end of a complete pandoc-rendered post. Gating on length
    # stops that fragment from nuking an otherwise-good 4KB clip.
    if len(text) < _WALL_TEXT_THRESHOLD:
        for marker in _FETCH_ERROR_MARKERS:
            if marker in text_lower:
                payload["_fetch_status"] = "failed"
                payload["_fetch_error"] = f"page contains error marker: {marker!r}"
                payload["_fetch_quality"] = "none"
                return payload

    # Weak (but valid) extraction — save as bookmark, skip LLM
    if (not text or len(text) < 100) and source.startswith(("http://", "https://")):
        payload["_fetch_quality"] = "weak"
        # _fetch_status stays 'ok' so caller saves it
        return payload

    return payload


def _get_concepts(notes_dir: Path) -> list[str]:
    """Get existing concept names from the concepts/ directory."""
    concepts_dir = notes_dir / "concepts"
    if not concepts_dir.exists():
        return []
    return [f.stem for f in sorted(concepts_dir.glob("*.md"))]


def _chinese_ratio(text: str) -> float:
    """Fraction of characters that look Chinese / CJK. Used to decide
    whether a body needs translation. Includes basic CJK + extension A."""
    if not text:
        return 0.0
    cjk = 0
    counted = 0
    for ch in text:
        cp = ord(ch)
        # Skip whitespace + punctuation from the denominator so a paragraph
        # of English with two Chinese chars doesn't get falsely classified.
        if ch.isspace() or not ch.isalnum() and cp < 0x4E00:
            continue
        counted += 1
        if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
            cjk += 1
    return cjk / counted if counted else 0.0


_JUNK_LINE_PATTERNS = [
    re.compile(r"轻触查看原文"),
    re.compile(r"向上滑动看下一个"),
    re.compile(r"Scan with Weixin"),
    re.compile(r"微信扫一扫可打开此内容"),
    re.compile(r"×\s*分析"),
    re.compile(r"\[Cancel\]\(javascript"),
    re.compile(r"\[Allow\]\(javascript"),
    re.compile(r"\[Got It\]\(javascript"),
    re.compile(r"Share\s+Comment\s+Favorite"),
    re.compile(r"Video Mini Program"),
    re.compile(r"轻点两下取消"),
    re.compile(r"use this Mini Program"),
    re.compile(r"^\s*[：:]\s*[，,。.]\s*$"),
]

_JUNK_BLOCK_PATTERNS = [
    re.compile(r"\n---\n.*?go\.bytebytego\.com.*?\n---\n", re.DOTALL),
    re.compile(r"\n---\n.*?\byou\.com\b.*?\n---\n", re.DOTALL | re.IGNORECASE),
    re.compile(r"\n---\n.*?Subscribe now.*?\n---\n", re.DOTALL | re.IGNORECASE),
    re.compile(r"\n---\n.*?你将获得.*?了解如何.*?\n---\n", re.DOTALL),
]


def _regex_clean(content: str) -> str:
    for pat in _JUNK_BLOCK_PATTERNS:
        content = pat.sub("\n---\n", content)

    lines = content.split("\n")
    cleaned_lines = []
    for line in lines:
        if any(p.search(line) for p in _JUNK_LINE_PATTERNS):
            continue
        cleaned_lines.append(line)
    content = "\n".join(cleaned_lines)

    content = re.sub(r"\n{4,}", "\n\n\n", content)
    return content.strip()


async def clean_content(content: str, provider: LLMProvider) -> str:
    """Remove ads, newsletter boilerplate, and social media UI junk.

    Two-pass: regex strips known patterns, then LLM removes embedded ads
    that regex can't catch (sponsored sections in newsletters, etc.).
    """
    if not content or len(content) < 200:
        return content
    content = _regex_clean(content)

    try:
        cleaned = await provider.chat([
            {"role": "system", "content": (
                "你是内容清洗器。删除文章中的嵌入式广告和推广段落，保留正文。\n"
                "广告特征：与文章主题无关的产品推荐、带推广链接的段落、"
                "'你将获得/了解更多/立即订阅/免费下载'等行动号召。\n"
                "同时删除文末独立的自我推广段落（如'联系我聊一聊'、'关注我的LinkedIn'）。\n"
                "保留所有正文、markdown格式、代码块、图片。直接输出结果。"
            )},
            {"role": "user", "content": content},
        ])
        cleaned = cleaned.strip()
        if len(cleaned) < len(content) * 0.3:
            return content
        return cleaned
    except Exception:
        return content


_TRANSLATE_GLOSSARY = """
### A. Keep English as-is (never translate — universally written in English in Chinese text)
API, SDK, PR, CI/CD, Docker, Git, LLM, Token, Benchmark

### B. Translate to Chinese, annotate English in parentheses on FIRST occurrence only
| English | Chinese |
|---------|---------|
| AI Agent | AI 智能体 |
| Agentic | 智能体化的 |
| Context Engineering | 上下文工程 |
| Prompt Engineering | 提示词工程 |
| Fine-tuning | 微调 |
| RAG / Retrieval-Augmented Generation | 检索增强生成 |
| Chain of Thought (CoT) | 思维链 |
| RLHF | 基于人类反馈的强化学习 |
| Embedding | 向量化 |
| Transformer | Transformer（不译，但可注释"一种神经网络架构"） |
| Pipeline | 流水线 |
| Workflow | 工作流 |
| Harness | 编排框架 |
| Scaffold / Scaffolding | 脚手架 |
| Vibe Coding | 凭感觉编程 |
| AI Wrapper | AI 套壳 |
| Hallucination | 幻觉 |
| Alignment | 对齐 |
| Guardrails | 护栏 |
| Grounding | 落地 |
| Inference | 推理 |
| Checkpoint | 检查点 |
| Sandbox | 沙箱 |

### C. Translate fully (no annotation needed — Chinese term is well-known)
| English | Chinese |
|---------|---------|
| Moat | 护城河 |
| Flywheel | 飞轮效应 |
| Boilerplate | 样板代码 |
| Latency | 延迟 |
| Throughput | 吞吐量 |
""".strip()

_TRANSLATE_PROMPT = """You are a professional translator. Translate the following markdown content from English to Simplified Chinese.

## Glossary

The glossary has three sections:
- **A. Keep English**: These are universally written in English in Chinese text (e.g. API, SDK, Token). Never translate.
- **B. Translate + annotate**: Use the Chinese translation. On FIRST occurrence, include the English in parentheses — e.g. "上下文工程（Context Engineering）". After that, Chinese only.
- **C. Translate fully**: The Chinese term is well-known enough that no English annotation is needed.

{glossary}

## Translation Principles

Rewrite the content into natural, engaging Chinese — not merely translate it. Every sentence should read as if a skilled Chinese native writer composed it from scratch.

- **Accuracy first**: Facts, data, numbers, proper nouns, and logic must match the original exactly
- **Natural flow**: Use idiomatic Chinese word order. Break long English sentences into shorter, natural Chinese ones. Interpret metaphors and idioms by intended meaning, not word-for-word
- **Anti-translationese**: Avoid unnecessary connectives (因此/然而/此外 used as crutches), passive voice abuse (被/由/受到), noun pile-ups, and stiff calques from English syntax
- **Terminology**: Use glossary translations consistently. For tech terms NOT in the glossary, keep the English original if it's commonly used as-is in Chinese tech circles (e.g. API, SDK, Docker, Git, PR)
- **Preserve format**: Keep ALL markdown formatting — headings, bold, italic, images, links, code blocks, blockquotes, lists
- **Proactive interpretation**: For jargon or concepts the reader may lack context for, add a BRIEF explanation in bold parentheses （**解释**）. Use sparingly — only where genuinely needed
- **Do NOT add** any translator's notes, preface, or postscript. Output ONLY the translated text

## Source Text

{content}"""


async def maybe_translate_to_chinese(
    content: str,
    provider: LLMProvider,
    *,
    threshold: float = 0.20,
    max_input_chars: int = 30_000,
) -> str | None:
    """If ``content`` is mostly non-Chinese, return a high-quality Chinese
    translation using baoyu-style principles; otherwise None.

    Translation approach adapted from github.com/JimLiu/baoyu-skills:
    glossary-driven, anti-translationese, natural Chinese voice.
    """
    if not content or len(content) > max_input_chars:
        return None
    if _chinese_ratio(content) >= threshold:
        return None

    system = _TRANSLATE_PROMPT.format(
        glossary=_TRANSLATE_GLOSSARY,
        content="",
    ).rsplit("## Source Text", 1)[0].strip()
    try:
        translated = await provider.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ])
        translated = translated.strip()
        if _chinese_ratio(translated) < 0.3:
            return None
        return translated
    except Exception:
        return None


CLIP_CATEGORIES = [
    "ai-practice",       # AI 工具实践：怎么用 Claude Code / Codex / prompt 技巧 / AI workflow
    "ai-architecture",   # AI 原理：LLM 底层、Agent 架构、模型设计、系统原理
    "product",           # 产品思维：产品设计、用户体验、商业模式
    "engineering",       # 工程实践：云基础设施、后端、前端、系统架构、编码实践
    "learning",          # 学习方法：知识管理、认知科学、教学方法
    "career",            # 成长：职业发展、思维模式、行业趋势
]

CLIP_CATEGORIES_STR = ", ".join(CLIP_CATEGORIES)


async def process_clip(
    content: str,
    title: str,
    profile: Profile,
    provider: LLMProvider,
    language: Language,
    notes_dir: Path | None = None,
) -> dict:
    """Lightweight LLM processing: summarize, relate, classify, extract.

    1 LLM call, returns:
    {summary, relevance, related_concepts, auto_tags, topic, takeaways}
    """
    domains = list(profile.skills.domains.keys())
    gaps: list[str] = []
    for d in profile.skills.domains.values():
        gaps.extend(d.gaps)
    for i in profile.skills.integrations.values():
        gaps.extend(i.gaps)
    gaps = list(dict.fromkeys(gaps))

    concepts = _get_concepts(notes_dir) if notes_dir else []

    if language.value == "zh":
        lang_hint = (
            "All string values in the JSON response (summary, relevance, "
            "related_concepts, auto_tags, takeaways) MUST be in Simplified Chinese (中文)"
            "，无论原文是什么语言。即使原文是英文 / 日文 / 任何语言，"
            "summary、relevance、takeaways 必须翻译成中文。topic 仍是英文标识符。"
        )
    else:
        lang_hint = "All string values in the JSON response must be in English."
    gaps_str = ", ".join(gaps[:20]) if gaps else "(none)"
    concepts_str = ", ".join(concepts[:30]) if concepts else "(none)"

    prompt = (
        "You are a knowledge management assistant. The user just clipped a fragment.\n\n"
        f"User skill gaps: {gaps_str}\n"
        f"Existing concepts: {concepts_str}\n\n"
        f"Fragment:\n{title}\n{content[:3000]}\n\n"
        "Reply in JSON:\n"
        "{\n"
        '  "summary": "one sentence summarizing what this is about",\n'
        '  "relevance": "one sentence on what this means for the user given their profile",\n'
        '  "related_concepts": ["concept1", "concept2"],\n'
        '  "auto_tags": ["tag1", "tag2", "tag3"],\n'
        f'  "topic": "MUST be one of: {CLIP_CATEGORIES_STR}",\n'
        '  "takeaways": ["核心要点1", "核心要点2", "核心要点3"],\n'
        '  "diagram": "mermaid code or empty string"\n'
        "}\n\n"
        "takeaways: Extract 3-5 key takeaways from the fragment. Each should be a "
        "complete, self-contained sentence that captures an actionable insight or "
        "important idea. The reader should understand the article's value from "
        "takeaways alone without reading the full text.\n\n"
        "diagram: Decide if this content benefits from a visual diagram. "
        "Generate a diagram ONLY for content with clear structure: architecture, "
        "multi-step processes, comparisons, timelines, or concept hierarchies. "
        "Do NOT generate diagrams for opinion pieces, short tips, or narrative essays. "
        "If a diagram is useful, output valid Mermaid code (mindmap, flowchart, or graph). "
        "Use Chinese labels. If no diagram is needed, output empty string \"\".\n"
        "Mermaid mindmap example:\n"
        "mindmap\n"
        "  root((主题))\n"
        "    分支1\n"
        "      细节A\n"
        "      细节B\n"
        "    分支2\n"
        "      细节C\n\n"
        f"topic: Pick the SINGLE best match from [{CLIP_CATEGORIES_STR}]. "
        "ai-practice = how to USE AI tools (Claude Code, Codex, prompts, workflows). "
        "ai-architecture = how AI WORKS internally (LLM internals, agent architecture, system design). "
        "product = product design, UX, business models. "
        "engineering = cloud infra, backend, frontend, coding practices. "
        "learning = learning methods, knowledge management, cognitive science. "
        "career = career growth, mindset, industry trends.\n\n"
        f"{lang_hint}"
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
        topic = data.get("topic", "ai-practice")
        if topic not in CLIP_CATEGORIES:
            topic = "ai-practice"
        return {
            "summary": data.get("summary", ""),
            "relevance": data.get("relevance", ""),
            "related_concepts": data.get("related_concepts", [])[:3],
            "auto_tags": data.get("auto_tags", [])[:5],
            "topic": topic,
            "takeaways": data.get("takeaways", [])[:5],
            "diagram": data.get("diagram", ""),
            "_llm_status": "ok",
            "_llm_error": None,
        }
    except Exception as exc:
        fallback = _fallback_process(content, title)
        fallback["_llm_status"] = "failed"
        fallback["_llm_error"] = str(exc) or exc.__class__.__name__
        return fallback


def _fallback_process(content: str, title: str) -> dict:
    """Fallback when LLM is unavailable: extract keywords, guess topic."""
    words = re.findall(r"[a-zA-Z\u4e00-\u9fff]{2,}", (title + " " + content)[:500])
    word_freq: dict[str, int] = {}
    for w in words:
        lower = w.lower()
        word_freq[lower] = word_freq.get(lower, 0) + 1
    sorted_words = sorted(word_freq.items(), key=lambda x: -x[1])
    tags = [w for w, _ in sorted_words[:5] if len(w) > 2]

    topic = "ai-practice"
    content_lower = (title + " " + content).lower()
    for cat in CLIP_CATEGORIES:
        if cat.replace("-", " ") in content_lower or cat.replace("-", "") in content_lower:
            topic = cat
            break

    return {
        "summary": "",
        "relevance": "",
        "related_concepts": [],
        "auto_tags": tags,
        "topic": topic,
        "takeaways": [],
        "diagram": "",
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


def _wechat_image_slug(stem: str) -> str:
    """Slugify article title for use as image filename prefix.

    Mirrors ``config.save_clip``'s slug logic so image filenames stay in
    lockstep with the note filename — both lose punctuation (full-width
    ``，`` ``。`` included; they break URL parsing in some markdown
    renderers) and keep CJK + alnum + ``_``. Without this, a note's URL
    inside the markdown could end up with ``，`` / ``。`` which some
    renderers fail to resolve.
    """
    s = re.sub(r"[^\w\s-]", "", stem)
    s = re.sub(r"[\s_]+", "-", s).strip("-").lower()
    return s[:60] if s else "wechat-article"


def relocate_wechat_images(content: str, md_path, notes_dir) -> str:
    """Move WeChat tool's per-article ``images/`` to vault-wide ``notes_dir/images/``
    with a per-article prefix, and rewrite markdown refs to standard relative
    paths that any markdown renderer (GUI client, Obsidian, GitHub, ...) accepts.

    The wechat-article-to-markdown tool produces:
        <tempdir>/<title>/<title>.md     ← references ``images/img_001.png``
        <tempdir>/<title>/images/img_001.png

    Notes are saved at depth 2 under the vault (``clips/<topic>/*.md``).
    We:

    1. Copy each image to ``notes_dir/images/<slug>-<original_name>``
       (vault-wide, prefixed to avoid ``img_001.png`` collisions between
       articles).
    2. Rewrite ``![alt](images/img_001.png)`` → ``![](../../images/<slug>-img_001.png)``
       — standard markdown, relative to the note's parent dir.

    Caller passes ``md_path`` while the tempdir is still alive.
    """
    import shutil
    from pathlib import Path

    img_dir = Path(md_path).parent / "images"
    if not img_dir.exists():
        return content

    slug = _wechat_image_slug(Path(md_path).stem)
    dest_dir = Path(notes_dir) / "images"
    dest_dir.mkdir(parents=True, exist_ok=True)

    rename_map: dict[str, str] = {}
    for img in img_dir.iterdir():
        if not img.is_file():
            continue
        new_name = f"{slug}-{img.name}"
        dest = dest_dir / new_name
        if not dest.exists():
            shutil.copy2(str(img), str(dest))
        rename_map[img.name] = new_name

    if not rename_map:
        return content

    # Percent-encode the URL portion so Swift / SwiftUI's URL(string:) (used
    # by MarkdownUI in the Mac client) can parse non-ASCII filenames. The
    # files themselves stay CJK on disk — only the markdown URL text gets
    # encoded. Obsidian / VS Code / GitHub all accept this form too.
    from urllib.parse import quote

    def _rewrite(match: re.Match) -> str:
        alt = match.group(1)
        original = match.group(2)
        renamed = rename_map.get(original, original)
        encoded = quote(renamed, safe="-_.")
        return f"![{alt}](../../images/{encoded})"

    return re.sub(r"!\[([^\]]*)\]\(images/([^)]+)\)", _rewrite, content)


async def _fetch_wechat_clip(source: str) -> dict:
    """Fetch WeChat article content using wechat-article-to-markdown tool,
    falling back to markdown.new browser rendering on failure."""
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    content: str | None = None

    if shutil.which("wechat-article-to-markdown"):
        with tempfile.TemporaryDirectory(prefix="neocortex-wechat-") as tmpdir:
            result = subprocess.run(
                ["wechat-article-to-markdown", "-o", tmpdir, source],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                md_path = _parse_wechat_output(result.stdout)
                if md_path is not None and md_path.exists():
                    content = md_path.read_text(encoding="utf-8")
                    from neocortex.config import get_notes_dir
                    content = relocate_wechat_images(content, md_path, get_notes_dir())

    if not content:
        content = await _fetch_wechat_via_markdown_new(source)

    if not content:
        raise ValueError(
            "WeChat article fetch failed (both wechat-article-to-markdown and markdown.new).\n"
            "Or paste the article text directly: neocortex clip --paste"
        )

    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else source

    body = content[:_MAX_CLIP_CONTENT_CHARS] if content else source
    return {
        "title": title,
        "content": _with_source_link(body, source),
        "clip_type": "bookmark",
        "source": source,
    }


async def _fetch_wechat_via_markdown_new(source: str) -> str | None:
    """Fallback: fetch WeChat article via markdown.new browser rendering.

    Uses curl because httpx gets 403 from markdown.new (it fingerprints
    HTTP/2 + library-style TLS, which curl avoids).
    """
    import subprocess

    url = f"https://markdown.new/{source}?method=browser"
    try:
        result = subprocess.run(
            ["curl", "-sS", "-L", "--max-time", "60",
             "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
             url],
            capture_output=True, text=True, timeout=70,
        )
        if result.returncode != 0:
            return None
        text = result.stdout.strip()
        if len(text) < 80 or "环境异常" in text:
            return None
        body = re.sub(r"^.*?^Markdown Content:\s*\n", "", text,
                       count=1, flags=re.DOTALL | re.MULTILINE)
        body = _strip_wechat_ui_junk(body)
        return body.strip() if body.strip() else None
    except (subprocess.TimeoutExpired, OSError):
        return None


_WECHAT_JUNK_MARKERS = [
    "轻触查看原文",
    "向上滑动看下一个",
    "Got It](javascript",
    "Scan with Weixin",
    "微信扫一扫可打开此内容",
    "Cancel](javascript:void",
    "Video Mini Program Like",
    "轻点两下取消赞",
    "Share Comment Favorite",
]


def _strip_wechat_ui_junk(text: str) -> str:
    earliest = len(text)
    for marker in _WECHAT_JUNK_MARKERS:
        idx = text.find(marker)
        if idx != -1 and idx < earliest:
            earliest = idx
    if earliest < len(text):
        text = text[:earliest]
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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

    body = text[:_MAX_CLIP_CONTENT_CHARS]
    return {
        "title": title,
        "content": _with_source_link(body, source),
        "clip_type": "tweet",
        "source": source,
        "_fetch_status": "ok",
        "_fetch_error": None,
    }
