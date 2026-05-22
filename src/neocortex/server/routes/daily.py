"""GET /api/daily — read-only daily briefing for the GUI dashboard.

Default skips the per-clip LLM context-update pass (set ``llm=true`` to
opt in — adds 1–3s). Briefing is read-only: it does NOT advance
``next_surface`` schedules. Marking items surfaced is a separate future
endpoint so the user can do it explicitly via the GUI.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from neocortex.models import DailyBriefing, SurfaceUpdate
from neocortex.services.daily import build_briefing, mark_surfaced


class SurfaceRequest(BaseModel):
    clip_id: str = Field(..., min_length=1)
    absorbed: bool = False


def make_router(require_token) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["daily"])

    @router.get(
        "/daily",
        response_model=DailyBriefing,
        dependencies=[Depends(require_token)],
    )
    async def daily_endpoint(llm: bool = False) -> DailyBriefing:
        from neocortex.config import get_notes_dir, load_config, load_profile

        cfg = load_config()
        profile = load_profile()
        notes_dir = get_notes_dir()

        return await build_briefing(
            notes_dir=notes_dir,
            cfg=cfg,
            profile=profile,
            lang=cfg.output_settings.language,
            with_llm=llm,
        )

    @router.post(
        "/daily/surface",
        response_model=SurfaceUpdate,
        dependencies=[Depends(require_token)],
    )
    async def surface_endpoint(req: SurfaceRequest) -> SurfaceUpdate:
        from neocortex.config import get_notes_dir

        result = mark_surfaced(
            notes_dir=get_notes_dir(),
            clip_id=req.clip_id,
            absorbed=req.absorbed,
        )
        if result is None:
            raise HTTPException(status_code=404, detail=f"clip {req.clip_id!r} not found")
        return result

    return router
