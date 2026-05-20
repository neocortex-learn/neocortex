"""POST /api/clip — capture a URL/text fragment.

Wraps ``neocortex.services.clip.clip_text``. Returns a full ClipResult so
the client can render the same 4-section feedback the CLI shows (📈 / 🌱 /
🔗 / status). Fetch hard-failures come back as 200 + aborted=true (the
request itself was valid; upstream fetch failed — that's business state,
not protocol error).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from neocortex.models import ClipResult
from neocortex.services.clip import clip_text


class ClipRequest(BaseModel):
    """Body for POST /api/clip."""
    source: str = Field(..., min_length=1, description="URL, plain text, or file path")
    process: bool | None = Field(
        default=None,
        description=(
            "True = force LLM tagging; False = force skip; "
            "None = use cfg.clip_default_process (Q11 default-on)."
        ),
    )


def make_router(require_token) -> APIRouter:
    """Build the clip router with the supplied auth dependency."""
    router = APIRouter(prefix="/api", tags=["clip"])

    @router.post(
        "/clip",
        response_model=ClipResult,
        dependencies=[Depends(require_token)],
    )
    async def clip_endpoint(req: ClipRequest) -> ClipResult:
        from neocortex.config import get_notes_dir, load_config, load_profile

        cfg = load_config()
        profile = load_profile()
        notes_dir = get_notes_dir()

        return await clip_text(
            req.source,
            process=req.process,
            notes_dir=notes_dir,
            cfg=cfg,
            profile=profile,
            lang=cfg.output_settings.language,
        )

    return router
