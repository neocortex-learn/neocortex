"""SQLite FTS5 full-text search index + vector semantic search for Neocortex notes."""

from __future__ import annotations

import math
import re
import sqlite3
import struct
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

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
        """Create the FTS5 virtual table and embedding table if they do not exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                    filename,
                    title,
                    content,
                    tokenize='unicode61'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS note_embeddings (
                    filename TEXT PRIMARY KEY,
                    embedding BLOB NOT NULL
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    def _get_embedding_model(self):
        """Lazily load the fastembed model. Returns None if fastembed is not installed."""
        if not hasattr(self, "_embed_model"):
            try:
                from fastembed import TextEmbedding
                self._embed_model = TextEmbedding("BAAI/bge-small-en-v1.5")
            except ImportError:
                self._embed_model = None
        return self._embed_model

    def index_note(self, filename: str, title: str, content: str) -> None:
        """Index or update a single note (FTS5 + embedding)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM notes_fts WHERE filename = ?", (filename,))
            conn.execute(
                "INSERT INTO notes_fts (filename, title, content) VALUES (?, ?, ?)",
                (filename, title, content),
            )
        self.index_note_embedding(filename, content)

    def index_note_embedding(self, filename: str, content: str) -> None:
        """Generate and store the embedding vector for a single note."""
        model = self._get_embedding_model()
        if model is None:
            return
        text = content[:2000]
        embedding = list(model.embed([text]))[0]
        blob = struct.pack(f"{len(embedding)}f", *embedding)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO note_embeddings (filename, embedding) VALUES (?, ?)",
                (filename, blob),
            )

    def index_all(self, notes_dir: Path) -> int:
        """Index all .md files under *notes_dir*. Returns the number indexed."""
        count = 0
        with self._connect() as conn:
            conn.execute("DELETE FROM notes_fts")
            conn.execute("DELETE FROM note_embeddings")
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
        model = self._get_embedding_model()
        if model is not None:
            for md_file in sorted(notes_dir.glob("*.md")):
                try:
                    content = md_file.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                self.index_note_embedding(md_file.name, content)
        return count

    def index_all_with_progress(self, notes_dir: Path, on_fts_done=None, on_embed_progress=None) -> int:
        """Index all .md files with progress callbacks.

        *on_fts_done(count)* is called after FTS5 indexing finishes.
        *on_embed_progress(current, total)* is called after each embedding.
        """
        count = 0
        with self._connect() as conn:
            conn.execute("DELETE FROM notes_fts")
            conn.execute("DELETE FROM note_embeddings")
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

        if on_fts_done is not None:
            on_fts_done(count)

        model = self._get_embedding_model()
        if model is not None:
            md_files = sorted(notes_dir.glob("*.md"))
            total = len(md_files)
            for i, md_file in enumerate(md_files):
                try:
                    content = md_file.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                self.index_note_embedding(md_file.name, content)
                if on_embed_progress is not None:
                    on_embed_progress(i + 1, total)

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

    def semantic_search(self, query: str, limit: int = 20) -> list[dict]:
        """Vector semantic search. Returns ``[{filename, score}]``."""
        model = self._get_embedding_model()
        if model is None:
            return []
        query_embedding = list(model.embed([query]))[0]

        with self._connect() as conn:
            rows = conn.execute("SELECT filename, embedding FROM note_embeddings").fetchall()

        results: list[dict] = []
        for filename, blob in rows:
            dim = len(blob) // 4
            stored = struct.unpack(f"{dim}f", blob)
            sim = _cosine_similarity(query_embedding, stored)
            results.append({"filename": filename, "score": sim})

        results.sort(key=lambda x: -x["score"])
        return results[:limit]

    def hybrid_search(self, query: str, limit: int = 20) -> list[dict]:
        """Hybrid search: FTS5 + vector, merged and ranked."""
        fts_results = self.search(query, limit=limit * 2)
        vec_results = self.semantic_search(query, limit=limit * 2)
        return _merge_results(fts_results, vec_results, limit)

    def has_index(self) -> bool:
        """Return *True* if the index contains at least one row."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM notes_fts").fetchone()
            return row[0] > 0

    def has_embeddings(self) -> bool:
        """Return *True* if there are any stored embeddings."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM note_embeddings").fetchone()
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


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Compute cosine similarity between two vectors using pure Python."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _merge_results(fts: list[dict], vec: list[dict], limit: int) -> list[dict]:
    """Merge FTS5 and vector search results with weighted scoring."""
    scores: dict[str, dict] = {}

    for i, r in enumerate(fts):
        fn = r["filename"]
        scores[fn] = {
            "filename": fn,
            "title": r.get("title", ""),
            "snippet": r.get("snippet", ""),
            "fts_score": 1.0 / (i + 1),
            "vec_score": 0.0,
        }

    for r in vec:
        fn = r["filename"]
        if fn in scores:
            scores[fn]["vec_score"] = r["score"]
        else:
            scores[fn] = {
                "filename": fn,
                "title": "",
                "snippet": "",
                "fts_score": 0.0,
                "vec_score": r["score"],
            }

    for item in scores.values():
        item["score"] = 0.5 * item["fts_score"] + 0.5 * item["vec_score"]

    results = sorted(scores.values(), key=lambda x: -x["score"])
    return results[:limit]
