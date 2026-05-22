"""GET /api/search — FTS5 (+ optional semantic) over vault notes.

Wraps ``NoteIndex`` which already powers the CLI ``neocortex search``.
v0 returns FTS5 hits only; semantic blending stays opt-in via ``mode=hybrid``
because fastembed cold-start adds ~2s latency that would hurt the type-as-you-go
search box in the Mac client.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel


class SearchHit(BaseModel):
    filename: str
    title: str
    snippet: str = ""


class SearchResponse(BaseModel):
    query: str
    mode: str
    hits: list[SearchHit]


def make_router(require_token) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["search"])

    @router.get(
        "/search",
        response_model=SearchResponse,
        dependencies=[Depends(require_token)],
    )
    async def search_endpoint(
        q: str,
        limit: int = 20,
        mode: Literal["fts", "hybrid"] = "fts",
    ) -> SearchResponse:
        from neocortex.config import get_data_dir
        from neocortex.search import NoteIndex

        if not q.strip():
            raise HTTPException(status_code=400, detail="query 'q' is required")

        index = NoteIndex(get_data_dir() / "neocortex.sqlite")
        if not index.has_index():
            return SearchResponse(query=q, mode=mode, hits=[])

        try:
            raw = (
                index.hybrid_search(q, limit=limit)
                if mode == "hybrid"
                else index.search(q, limit=limit)
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"search failed: {exc}")

        # hybrid_search returns dicts with possibly missing 'snippet' (vector
        # hits don't carry one). Normalise to SearchHit shape.
        hits = [
            SearchHit(
                filename=item.get("filename", ""),
                title=item.get("title", "") or item.get("filename", ""),
                snippet=item.get("snippet", ""),
            )
            for item in raw
        ]
        return SearchResponse(query=q, mode=mode, hits=hits)

    return router
