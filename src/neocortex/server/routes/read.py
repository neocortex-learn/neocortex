"""POST /api/read — deep-note generation (long-running ~30s–3min).

Sync HTTP for v0 — caller (Mac client / CLI fallback / future iOS) just waits.
WebSocket progress streaming can be added later; for now the response body
includes elapsed_seconds so the UI can show "took 47s".
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from neocortex.models import ReadResult
from neocortex.services.read import read_url


class ReadRequest(BaseModel):
    source: str = Field(..., min_length=1, description="URL to deep-read")
    focus: str | None = Field(
        default=None,
        description="Optional 'focus on X' hint passed through to the prompt",
    )


def make_router(require_token) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["read"])

    @router.post(
        "/read",
        response_model=ReadResult,
        dependencies=[Depends(require_token)],
    )
    async def read_endpoint(req: ReadRequest) -> ReadResult:
        from neocortex.config import get_notes_dir, load_config, load_profile

        cfg = load_config()
        profile = load_profile()
        notes_dir = get_notes_dir()

        return await read_url(
            req.source,
            notes_dir=notes_dir,
            cfg=cfg,
            profile=profile,
            lang=cfg.output_settings.language,
            focus=req.focus,
        )

    return router
