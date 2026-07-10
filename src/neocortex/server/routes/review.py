"""POST /api/review/session + /api/review/action — GUI 复习闭环。

安全边界与其他 HTTP 端点一致：SecurityMiddleware（Host/Origin/Content-Type）
+ ``Depends(require_token)``。不使用 WebSocket 专用的 validate_ws_handshake。

- session：只有用户明确点击"开始复习"时调用；菜单刷新 / daily / 预取
  一律走 GET /api/daily（读）和 impression（记录曝光），不创建 session。
- action：event_id 幂等，重试同一 event_id 不会重复调度 / boost / 记录。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field


class SessionRequest(BaseModel):
    limit: int = Field(5, ge=1, description="服务端强制上限 5")
    entry_point: str = Field(..., min_length=1, max_length=64)


class ActionRequest(BaseModel):
    event_id: str = Field(..., min_length=8, max_length=128)
    action: str = Field(..., min_length=1, max_length=32)
    session_id: str | None = None
    card_id: str | None = None


def make_router(require_token) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["review"])

    def _store():
        from neocortex.config import get_data_dir
        from neocortex.services.review_events import ReviewEventStore

        return ReviewEventStore(get_data_dir() / "neocortex.sqlite")

    @router.post("/review/session", dependencies=[Depends(require_token)])
    async def create_session_endpoint(req: SessionRequest) -> dict:
        from neocortex.config import get_notes_dir
        from neocortex.services.review_events import create_review_session

        return create_review_session(
            get_notes_dir(), _store(),
            limit=req.limit, entry_point=req.entry_point,
        )

    @router.post("/review/action", dependencies=[Depends(require_token)])
    async def action_endpoint(req: ActionRequest) -> dict:
        from neocortex.config import get_notes_dir
        from neocortex.services.review_events import (
            ReviewFlowError,
            handle_review_action,
        )

        try:
            return handle_review_action(
                get_notes_dir(), _store(),
                event_id=req.event_id, action=req.action,
                session_id=req.session_id, card_id=req.card_id,
            )
        except ReviewFlowError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return router
