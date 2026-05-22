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


_SOURCE_LINE = re.compile(r'^source:\s*"?([^"\n]+?)"?\s*$', re.MULTILINE)
_TITLE_LINE = re.compile(r'^title:\s*"?([^"\n]+?)"?\s*$', re.MULTILINE)
_DATE_LINE = re.compile(r'^(?:date|created_at):\s*([^\n]+?)\s*$', re.MULTILINE)


def extract_frontmatter_meta(md_path: Path) -> dict[str, str]:
    """Return ``{title, source, created_at}`` parsed from the first frontmatter
    block. Missing fields come back as empty strings.

    Frontmatter must start at byte 0 with ``---\\n``; we don't try to parse
    YAML mid-file (those notes wouldn't be dedup candidates anyway). When
    ``title`` isn't in frontmatter, falls back to the first H1 heading.

    Shared between dedup scanning and the ``_reused_*`` helpers in services/
    so we don't keep two near-identical YAML mini-parsers in sync.
    """
    try:
        text = md_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {"title": md_path.stem, "source": "", "created_at": ""}

    front = ""
    if text.startswith("---"):
        end = text.find("\n---", 4)
        if end > 0:
            front = text[4:end]

    title = ""
    source = ""
    created_at = ""
    if front:
        if m := _TITLE_LINE.search(front):
            title = m.group(1).strip()
        if m := _SOURCE_LINE.search(front):
            source = m.group(1).strip()
        if m := _DATE_LINE.search(front):
            created_at = m.group(1).strip()

    # Fallback: first ``# `` heading in the body.
    if not title:
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
    if not title:
        title = md_path.stem

    return {"title": title, "source": source, "created_at": created_at}


def _extract_source(md_path: Path) -> str | None:
    """Legacy thin shim — prefer ``extract_frontmatter_meta`` in new code."""
    meta = extract_frontmatter_meta(md_path)
    return meta["source"] or None


def find_existing(notes_dir: Path, source: str) -> Path | None:
    """Return the existing note matching ``source`` (after normalisation),
    or None if no match. Returns the most recently modified one when
    multiple legacy duplicates exist.

    Lookup order:
      1. ``NoteIndex.note_sources`` SQLite table (O(log n) — populated by
         ``index_note`` for every clip/read written after this change).
      2. Filesystem fallback: ``rglob("*.md")`` + frontmatter scan, to
         cover legacy notes that pre-date the index. If we find one in the
         fallback, hand it back to the index so the next call is fast.

    Skip-listed in the FS scan: ``log.md`` / ``INDEX.md`` / ``overview.md``
    (knowledge base docs, not clips); hidden dirs (``.git``, ``.search.db``).
    """
    key = normalize_source_url(source)
    if key is None:
        return None
    if not notes_dir.exists():
        return None

    # 1. Fast path — SQLite lookup.
    indexed = _lookup_indexed_source(notes_dir, key)
    if indexed is not None:
        # File could have been deleted while still in the index — confirm
        # it's still there before handing back, otherwise fall through.
        if indexed.exists():
            return indexed

    # 2. Slow path — filesystem scan (one-time cost per legacy note).
    matches: list[Path] = []
    for md in notes_dir.rglob("*.md"):
        if any(part.startswith(".") for part in md.parts):
            continue
        if md.name in {"INDEX.md", "log.md", "overview.md"}:
            continue
        meta = extract_frontmatter_meta(md)
        if not meta["source"]:
            continue
        if normalize_source_url(meta["source"]) == key:
            matches.append(md)

    if not matches:
        return None
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    winner = matches[0]

    # Backfill the index so subsequent calls skip the FS scan.
    _backfill_indexed_source(notes_dir, winner)
    return winner


def _lookup_indexed_source(notes_dir: Path, normalized_key: str) -> Path | None:
    """SQLite probe; returns absolute path or None. Errors swallowed so a
    corrupt index just degrades to the FS fallback rather than crashing."""
    try:
        from neocortex.config import get_data_dir
        from neocortex.search import NoteIndex

        idx = NoteIndex(get_data_dir() / "neocortex.sqlite")
        rel = idx.find_filename_by_source(normalized_key)
        if rel is None:
            return None
        return notes_dir / rel
    except Exception:
        return None


def _backfill_indexed_source(notes_dir: Path, md_path: Path) -> None:
    """Push a legacy match into NoteIndex so the next lookup is O(log n).
    Best-effort — errors leave the row absent and we'll FS-scan again."""
    try:
        from neocortex.config import get_data_dir
        from neocortex.search import NoteIndex

        rel = str(md_path.relative_to(notes_dir))
        meta = extract_frontmatter_meta(md_path)
        content = md_path.read_text(encoding="utf-8", errors="ignore")
        NoteIndex(get_data_dir() / "neocortex.sqlite").index_note(
            rel, meta["title"], content,
        )
    except Exception:
        pass
