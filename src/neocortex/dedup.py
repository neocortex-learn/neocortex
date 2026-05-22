"""Source-URL dedup for clip / read.

Same URL submitted twice (via terminal + GUI, or just forgotten) should reuse
the existing note rather than fire a 30s–3min LLM pipeline + clutter the
vault with `-2.md` / `-3.md` copies.

Strategy:
    - URL inputs → normalise (strip common tracking params + trailing slash
      + fragment), then scan vault for any `.md` whose frontmatter `source:`
      matches the same normalised key.
    - Non-URL inputs (pasted text, ``source: manual``, empty) → opt out of
      dedup. Text content drift makes content-hash dedup brittle, and the
      cost of re-clipping a 2KB note is negligible anyway.

The vault scan is plain text matching on the first frontmatter block —
NoteIndex would be faster but isn't always populated for old notes, and
this code path runs at most once per clip / read.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Tracking params we strip when normalising. Conservative — only obvious
# attribution junk that doesn't affect what content the server serves.
TRACKING_PARAMS: frozenset[str] = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "msclkid", "yclid", "dclid",
    "ref", "ref_src", "ref_url", "source", "from",
    "mc_cid", "mc_eid", "_ga", "igshid",
    "spm", "share", "share_source", "share_token", "share_from",
    "scene", "srcid",
})

# WeChat article URLs use mid/idx/sn/chksm/__biz as the *real* article
# identifier — strip those and you'd collide unrelated articles.
WECHAT_KEEP: frozenset[str] = frozenset({"mid", "idx", "sn", "chksm", "__biz"})

# Frontmatter source values we treat as "no URL, opt out of dedup".
_OPT_OUT_SOURCES: frozenset[str] = frozenset({"manual", "", "-", "none"})


def normalize_source_url(raw: str) -> str | None:
    """Return canonical dedup key, or None if input opts out of dedup.

    Examples:
        "https://overreacted.io/before-you-memo/?utm_source=x" → "https://overreacted.io/before-you-memo"
        "https://x.com/a/status/123#frag"                     → "https://x.com/a/status/123"
        "manual"                                              → None
        ""                                                    → None
        "随便一段文字"                                        → None
    """
    if raw is None:
        return None
    s = raw.strip()
    if s.lower() in _OPT_OUT_SOURCES:
        return None
    if not s.startswith(("http://", "https://")):
        # Pasted text / unknown scheme — opt out.
        return None
    try:
        parts = urlsplit(s)
    except ValueError:
        return None
    if not parts.netloc:
        return None

    is_wechat = "mp.weixin.qq.com" in parts.netloc

    kept: list[tuple[str, str]] = []
    for k, v in parse_qsl(parts.query, keep_blank_values=True):
        kl = k.lower()
        if is_wechat and kl in WECHAT_KEEP:
            kept.append((k, v))
            continue
        if kl in TRACKING_PARAMS:
            continue
        kept.append((k, v))

    path = parts.path.rstrip("/") or "/"
    # Drop fragment — overwhelmingly used for in-page anchors that don't
    # change the article content.
    return urlunsplit((
        parts.scheme,
        parts.netloc.lower(),
        path,
        urlencode(kept),
        "",
    ))


_SOURCE_LINE = re.compile(r'^source:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)


def _extract_source(md_path: Path) -> str | None:
    """Read the first frontmatter block, return its `source:` value or None.

    Frontmatter must start at byte 0 with ``---\\n``; otherwise we don't try
    to parse mid-file (those notes won't be dedup-candidates anyway).
    """
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 4)
    if end < 0:
        return None
    m = _SOURCE_LINE.search(text[4:end])
    return m.group(1).strip() if m else None


def find_existing(notes_dir: Path, source: str) -> Path | None:
    """Return the existing note matching ``source`` (after normalisation),
    or None if no match. Returns the most recently modified one when
    multiple legacy duplicates exist.

    Skip-listed: ``log.md`` / ``INDEX.md`` / ``overview.md`` (knowledge
    base docs, not clips); hidden dirs (``.git``, ``.search.db``, etc.).
    """
    key = normalize_source_url(source)
    if key is None:
        return None
    if not notes_dir.exists():
        return None

    matches: list[Path] = []
    for md in notes_dir.rglob("*.md"):
        if any(part.startswith(".") for part in md.parts):
            continue
        if md.name in {"INDEX.md", "log.md", "overview.md"}:
            continue
        raw = _extract_source(md)
        if not raw:
            continue
        if normalize_source_url(raw) == key:
            matches.append(md)

    if not matches:
        return None
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]
