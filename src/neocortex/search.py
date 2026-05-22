"""SQLite FTS5 full-text search index + vector semantic search for Neocortex notes."""

from __future__ import annotations

import math
import re
import sqlite3
import struct
from pathlib import Path

def _normalize_source_from_content(content: str) -> str | None:
    """Extract the ``source:`` value from leading frontmatter and normalise it.

    Lives here (rather than via ``extract_frontmatter_meta``) to keep the
    SQLite write path zero-import-cost on the hot index_note loop —
    ``dedup.normalize_source_url`` is cheap and pure though, so we still
    call it for consistent stripping rules.
    """
    if not content.startswith("---"):
        return None
    end = content.find("\n---", 4)
    if end < 0:
        return None
    front = content[4:end]
    m = re.search(r'^source:\s*"?([^"\n]+?)"?\s*$', front, re.MULTILINE)
    if not m:
        return None
    from neocortex.dedup import normalize_source_url
    return normalize_source_url(m.group(1).strip())


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
            # Indexed normalised-URL → filename map for clip/read dedup.
            # Lookup is O(log n) vs the previous O(n) full-vault rglob,
            # which started hurting around 10k notes. Populated lazily by
            # ``index_note`` from frontmatter; legacy notes outside the index
            # still match via dedup.py's FS fallback scan.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS note_sources (
                    normalized_source TEXT NOT NULL,
                    filename          TEXT NOT NULL,
                    PRIMARY KEY (normalized_source, filename)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_note_sources_norm "
                "ON note_sources(normalized_source)"
            )

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
        """Index or update a single note (FTS5 + embedding + dedup source).

        We extract ``source:`` from the leading frontmatter (cheap regex, no
        YAML lib) and feed it into ``note_sources`` so dedup queries don't
        have to scan the whole vault. Notes without frontmatter ``source``
        simply don't register here — that's correct (they opt out of dedup).
        """
        with self._connect() as conn:
            conn.execute("DELETE FROM notes_fts WHERE filename = ?", (filename,))
            conn.execute(
                "INSERT INTO notes_fts (filename, title, content) VALUES (?, ?, ?)",
                (filename, title, content),
            )
            # Refresh the source row (rewrite same content with different
            # source URL is a rare but possible operation).
            conn.execute("DELETE FROM note_sources WHERE filename = ?", (filename,))
            normalized = _normalize_source_from_content(content)
            if normalized:
                conn.execute(
                    "INSERT OR REPLACE INTO note_sources "
                    "(normalized_source, filename) VALUES (?, ?)",
                    (normalized, filename),
                )
        self.index_note_embedding(filename, content)

    def find_filename_by_source(self, normalized_source: str) -> str | None:
        """Look up the indexed filename matching ``normalized_source`` (already
        run through ``dedup.normalize_source_url``). Returns None if no row
        matches — caller should then try the FS fallback for legacy notes.
        """
        if not normalized_source:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT filename FROM note_sources WHERE normalized_source = ? LIMIT 1",
                (normalized_source,),
            ).fetchone()
        return row[0] if row else None

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
            for md_file in sorted(notes_dir.rglob("*.md")):
                if "diagrams" in md_file.parts:
                    continue
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
                rel_path = str(md_file.relative_to(notes_dir))
                conn.execute(
                    "INSERT INTO notes_fts (filename, title, content) VALUES (?, ?, ?)",
                    (rel_path, title, content),
                )
                count += 1
        model = self._get_embedding_model()
        if model is not None:
            for md_file in sorted(notes_dir.rglob("*.md")):
                if "diagrams" in md_file.parts:
                    continue
                try:
                    content = md_file.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                self.index_note_embedding(str(md_file.relative_to(notes_dir)), content)
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
            for md_file in sorted(notes_dir.rglob("*.md")):
                if "diagrams" in md_file.parts:
                    continue
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
                rel_path = str(md_file.relative_to(notes_dir))
                conn.execute(
                    "INSERT INTO notes_fts (filename, title, content) VALUES (?, ?, ?)",
                    (rel_path, title, content),
                )
                count += 1

        if on_fts_done is not None:
            on_fts_done(count)

        model = self._get_embedding_model()
        if model is not None:
            md_files = sorted(f for f in notes_dir.rglob("*.md") if "diagrams" not in f.parts)
            total = len(md_files)
            for i, md_file in enumerate(md_files):
                try:
                    content = md_file.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                self.index_note_embedding(str(md_file.relative_to(notes_dir)), content)
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
        query_vec = list(model.embed([query]))[0]
        query_norm = math.sqrt(sum(x * x for x in query_vec))
        if query_norm == 0:
            return []

        with self._connect() as conn:
            rows = conn.execute("SELECT filename, embedding FROM note_embeddings").fetchall()

        results: list[dict] = []
        for filename, blob in rows:
            dim = len(blob) // 4
            stored = struct.unpack(f"{dim}f", blob)
            # Fast dot product + norm (skip full cosine for non-candidates)
            dot = sum(x * y for x, y in zip(query_vec, stored))
            if dot <= 0:
                continue
            stored_norm = math.sqrt(sum(x * x for x in stored))
            if stored_norm == 0:
                continue
            sim = dot / (query_norm * stored_norm)
            if sim > 0.3:  # Only keep relevant results
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
