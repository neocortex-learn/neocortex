"""SQLite FTS5 full-text search index for Neocortex notes."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

_CJK_RE = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"
    r"\U00020000-\U0002a6df\U0002a700-\U0002ebef"
    r"\u3040-\u309f\u30a0-\u30ff"
    r"\uac00-\ud7af]"
)


class NoteIndex:
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the FTS5 virtual table if it does not exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                    filename,
                    title,
                    content,
                    tokenize='unicode61'
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    def index_note(self, filename: str, title: str, content: str) -> None:
        """Index or update a single note."""
        with self._connect() as conn:
            conn.execute("DELETE FROM notes_fts WHERE filename = ?", (filename,))
            conn.execute(
                "INSERT INTO notes_fts (filename, title, content) VALUES (?, ?, ?)",
                (filename, title, content),
            )

    def index_all(self, notes_dir: Path) -> int:
        """Index all .md files under *notes_dir*. Returns the number indexed."""
        count = 0
        with self._connect() as conn:
            conn.execute("DELETE FROM notes_fts")
            for md_file in sorted(notes_dir.glob("*.md")):
                try:
                    content = md_file.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                title = md_file.stem
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("# "):
                        title = stripped[2:].strip()
                        break
                conn.execute(
                    "INSERT INTO notes_fts (filename, title, content) VALUES (?, ?, ?)",
                    (md_file.name, title, content),
                )
                count += 1
        return count

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """FTS5 search. Returns ``[{filename, title, snippet}]``.

        CJK terms are automatically converted to prefix queries so that
        a search for e.g. "事务" matches the token "事务隔离级别与" produced
        by the ``unicode61`` tokenizer.
        """
        fts_query = _prepare_query(query)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT filename, title, snippet(notes_fts, 2, '>>>', '<<<', '...', 30)
                FROM notes_fts
                WHERE notes_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        return [
            {"filename": r[0], "title": r[1], "snippet": r[2]}
            for r in rows
        ]

    def has_index(self) -> bool:
        """Return *True* if the index contains at least one row."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM notes_fts").fetchone()
            return row[0] > 0


def _has_cjk(text: str) -> bool:
    """Return *True* if *text* contains any CJK character."""
    return bool(_CJK_RE.search(text))


def _prepare_query(query: str) -> str:
    """Convert a user query into a valid FTS5 MATCH expression.

    The ``unicode61`` tokenizer groups consecutive CJK characters into a
    single token (no word-boundary splitting for CJK).  A user searching
    for "事务" would not match the token "事务隔离级别与" unless we use a
    prefix query.  This function splits the query into whitespace-delimited
    terms and appends ``*`` to any term that contains CJK characters, turning
    it into a prefix query.  Pure-ASCII terms are left as-is so that exact
    word matching still works for English content.
    """
    terms = query.split()
    if not terms:
        return query
    prepared: list[str] = []
    for term in terms:
        if _has_cjk(term) and not term.endswith("*"):
            prepared.append(f"{term}*")
        else:
            prepared.append(term)
    return " ".join(prepared)
