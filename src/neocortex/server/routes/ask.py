"""POST /api/ask — single-turn Q&A.

Sync HTTP (one LLM round-trip + cheap evaluator). For multi-turn chat the
client should keep its own history and call this endpoint per turn; the
server is stateless on purpose so multiple GUI windows don't fight over
a shared session.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from neocortex.models import AskResult
from neocortex.services.ask import ask_question


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="User's question")


def make_router(require_token) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["ask"])

    @router.post(
        "/ask",
        response_model=AskResult,
        dependencies=[Depends(require_token)],
    )
    async def ask_endpoint(req: AskRequest) -> AskResult:
        from neocortex.config import get_notes_dir, load_config, load_profile

        cfg = load_config()
        profile = load_profile()
        notes_dir = get_notes_dir()

        return await ask_question(
            req.question,
            notes_dir=notes_dir,
            cfg=cfg,
            profile=profile,
            lang=cfg.output_settings.language,
        )

    return router
