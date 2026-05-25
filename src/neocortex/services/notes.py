"""Note-level operations (read / delete / future search / metadata).

S0-extension 2026-05-20: split from services.clip so deletion can be reused
by the upcoming Mac client trash button, future iOS share extension, and
any CLI cleanup tool — without bouncing through cmd_clip.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path


def _read_frontmatter(text: str) -> dict[str, str]:
    """Cheap key→value frontmatter parser (no full YAML)."""
    out: dict[str, str] = {}
    if not text.startswith("---"):
        return out
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i] == "---":
            break
        if ":" in lines[i]:
            k, _, v = lines[i].partition(":")
            out[k.strip()] = v.strip()
    return out


def _parse_related_concepts(text: str) -> list[str]:
    m = re.search(r'^related_concepts:\s*\[([^\]]*)\]', text, re.MULTILINE)
    if not m:
        return []
    return re.findall(r'"([^"]*)"', m.group(1))


def _reverse_concept_link(notes_dir: Path, clip_id: str, concept_name: str) -> bool:
    """Remove ``clip:<id>`` from a concept page's source_notes and
    decrement its evidence_count. Returns True if the page was modified."""
    slug = concept_name.strip().lower().replace(" ", "-")
    if not slug:
        return False
    page = notes_dir / "concepts" / f"{slug}.md"
    if not page.exists():
        return False
    content = page.read_text(encoding="utf-8")
    ref = f"clip:{clip_id}"
    if ref not in content:
        return False

    def _strip(match: re.Match) -> str:
        items = re.findall(r'"([^"]*)"', match.group(1))
        items = [x for x in items if x != ref]
        return "source_notes: [" + ", ".join(f'"{x}"' for x in items) + "]"

    content = re.sub(r'source_notes:\s*\[([^\]]*)\]', _strip, content, count=1)

    def _dec(match: re.Match) -> str:
        return f"evidence_count: {max(0, int(match.group(1)) - 1)}"

    content = re.sub(r'^evidence_count:\s*(\d+)', _dec, content,
                     count=1, flags=re.MULTILINE)
    page.write_text(content, encoding="utf-8")
    return True


def delete_note(notes_dir: Path, file_path: Path, *, db_path: Path | None = None) -> dict:
    """Move a note file to system Trash and reverse its concept references.

    Safety rules (all enforced):
        - file_path MUST be a real file under notes_dir (defeats ../ escape)
        - .md only (refuse to delete arbitrary types)
        - If it's a clip with related_concepts, undo each concept page link
        - Remove from SQLite FTS5 + embeddings (best-effort)
        - Use NSWorkspace recycle (Trash) so the user can recover

    Returns a small report dict for the UI to show.
    """
    file_path = file_path.resolve()
    notes_dir = notes_dir.resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"not a file: {file_path}")
    if not str(file_path).startswith(str(notes_dir) + "/"):
        raise PermissionError(f"path escapes vault: {file_path}")
    if file_path.suffix.lower() != ".md":
        raise PermissionError(f"refuse to delete non-md: {file_path}")

    text = file_path.read_text(encoding="utf-8")
    fm = _read_frontmatter(text)
    clip_id = fm.get("id", "")
    concepts = _parse_related_concepts(text)

    reversed_concepts: list[str] = []
    if clip_id and concepts:
        for c in concepts:
            if _reverse_concept_link(notes_dir, clip_id, c):
                reversed_concepts.append(c)

    # SQLite index cleanup (best-effort; missing tables = silently skip)
    indexed_removed = 0
    if db_path and db_path.exists():
        try:
            rel = str(file_path.relative_to(notes_dir))
        except ValueError:
            rel = file_path.name
        try:
            with sqlite3.connect(db_path) as conn:
                cur = conn.execute("DELETE FROM notes_fts WHERE filename = ?", (rel,))
                indexed_removed = cur.rowcount
                try:
                    conn.execute("DELETE FROM note_embeddings WHERE filename = ?", (rel,))
                except sqlite3.OperationalError:
                    pass
                # Also clear the dedup-source row so re-clipping the same URL
                # isn't blocked by a stale entry pointing at the deleted file.
                try:
                    conn.execute("DELETE FROM note_sources WHERE filename = ?", (rel,))
                except sqlite3.OperationalError:
                    pass
                conn.commit()
        except sqlite3.Error:
            pass

    # Move to system Trash via Foundation (NSFileManager.trashItem).
    # Falls back to os.unlink if PyObjC isn't available.
    trashed = False
    try:
        from Foundation import NSURL, NSFileManager
        url = NSURL.fileURLWithPath_(str(file_path))
        ok, _newURL, _err = (
            NSFileManager.defaultManager()
            .trashItemAtURL_resultingItemURL_error_(url, None, None)
        )
        trashed = bool(ok)
    except Exception:
        trashed = False

    if not trashed:
        # Last resort: hard delete (still safe since we already validated path)
        file_path.unlink()

    return {
        "deleted": str(file_path),
        "trashed": trashed,
        "reversed_concepts": reversed_concepts,
        "indexed_removed": indexed_removed,
    }
