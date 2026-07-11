"""P0 Inbox actions and Top of Mind configuration routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from neocortex.models import (
    InboxActionResponse,
    InboxListResponse,
    TopOfMindResponse,
)


class InboxActionRequest(BaseModel):
    action_id: str = Field(..., min_length=8, max_length=128)
    clip_id: str = Field(..., min_length=1, max_length=128)
    action: str = Field(..., min_length=1, max_length=32)
    target_action_id: str | None = Field(None, min_length=8, max_length=128)


class TopOfMindRequest(BaseModel):
    topics: list[str] = Field(default_factory=list)


def _normalise_topics(topics: list[str]) -> list[str]:
    normalised: list[str] = []
    seen: set[str] = set()
    for topic in topics:
        cleaned = " ".join(topic.split())
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalised.append(cleaned)
    if len(normalised) > 3:
        raise HTTPException(status_code=422, detail="Top of Mind supports at most 3 topics")
    return normalised


def make_router(require_token) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["inbox"])

    def _store():
        from neocortex.config import get_data_dir
        from neocortex.services.inbox import InboxEventStore

        return InboxEventStore(get_data_dir() / "neocortex.sqlite")

    @router.get(
        "/inbox",
        response_model=InboxListResponse,
        dependencies=[Depends(require_token)],
    )
    async def inbox_endpoint() -> InboxListResponse:
        from neocortex.config import get_notes_dir
        from neocortex.services.inbox import list_inbox

        return list_inbox(get_notes_dir())

    @router.post(
        "/inbox/action",
        response_model=InboxActionResponse,
        dependencies=[Depends(require_token)],
    )
    async def inbox_action_endpoint(req: InboxActionRequest) -> InboxActionResponse:
        from neocortex.config import get_notes_dir
        from neocortex.services.inbox import InboxFlowError, handle_inbox_action

        try:
            return handle_inbox_action(
                get_notes_dir(), _store(), action_id=req.action_id,
                clip_id=req.clip_id, action=req.action,
                target_action_id=req.target_action_id,
            )
        except InboxFlowError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    @router.get(
        "/top-of-mind",
        response_model=TopOfMindResponse,
        dependencies=[Depends(require_token)],
    )
    async def get_top_of_mind_endpoint() -> TopOfMindResponse:
        from neocortex.config import load_config

        return TopOfMindResponse(topics=load_config().top_of_mind)

    @router.put(
        "/top-of-mind",
        response_model=TopOfMindResponse,
        dependencies=[Depends(require_token)],
    )
    async def set_top_of_mind_endpoint(req: TopOfMindRequest) -> TopOfMindResponse:
        from neocortex.config import get_notes_dir, load_config, save_config

        topics = _normalise_topics(req.topics)
        # Materialising a previously implicit default config must preserve the
        # currently resolved vault (not AppConfig's legacy standalone default).
        active_notes_dir = get_notes_dir()
        config = load_config()
        if config.top_of_mind != topics:
            config.top_of_mind = topics
            config.output_settings.notes_dir = str(active_notes_dir)
            save_config(config)
        return TopOfMindResponse(topics=topics)

    return router
