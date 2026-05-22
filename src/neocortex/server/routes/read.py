"""POST /api/read and WebSocket /api/read/ws — deep-note generation.

HTTP variant: sync, blocks for 30s–3min, returns final ReadResult. Used by
CLI fallback and any client that doesn't speak WebSocket.

WebSocket variant: streams progress events live so the GUI can show
``fetch → outline → chunk 3/8 → save`` instead of a frozen spinner. Auth
must be done manually here because Starlette's BaseHTTPMiddleware doesn't
intercept the ``websocket`` ASGI scope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from neocortex.models import ReadResult
from neocortex.server.security import validate_ws_handshake
from neocortex.services.read import read_url


class ReadRequest(BaseModel):
    source: str = Field(..., min_length=1, description="URL to deep-read")
    focus: str | None = Field(
        default=None,
        description="Optional 'focus on X' hint passed through to the prompt",
    )


def make_router(require_token, *, expected_token: str | None = None,
                expected_host: str | None = None) -> APIRouter:
    """Build the read router.

    ``expected_token`` / ``expected_host`` enable the WebSocket auth path.
    They're optional so existing call sites (`make_router(require_token)`) keep
    working — WS just won't be mounted when they're missing.
    """
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

    if expected_token is None or expected_host is None:
        return router

    @router.websocket("/read/ws")
    async def read_ws(websocket: WebSocket) -> None:
        # Host / origin / bearer-token checks all live in security.py so the
        # WS path tracks the HTTP middleware policy automatically.
        if not await validate_ws_handshake(
            websocket,
            expected_token=expected_token,
            expected_host=expected_host,
        ):
            return

        await websocket.accept()

        # 4. Receive {source, focus?} as the first JSON message.
        try:
            payload = await websocket.receive_json()
            req = ReadRequest(**payload)
        except Exception as exc:  # noqa: BLE001
            await websocket.send_json({"type": "error", "message": f"bad request: {exc}"})
            await websocket.close(code=1003)
            return

        from neocortex.config import get_notes_dir, load_config, load_profile

        cfg = load_config()
        profile = load_profile()
        notes_dir = get_notes_dir()

        client_alive = True

        async def on_progress(phase: str, payload: dict) -> None:
            nonlocal client_alive
            if not client_alive:
                return
            try:
                await websocket.send_json({"type": "progress", "phase": phase, **payload})
            except Exception:
                client_alive = False

        try:
            result = await read_url(
                req.source,
                notes_dir=notes_dir,
                cfg=cfg,
                profile=profile,
                lang=cfg.output_settings.language,
                focus=req.focus,
                on_progress=on_progress,
            )
        except Exception as exc:  # noqa: BLE001
            try:
                await websocket.send_json({"type": "error", "message": str(exc)})
                await websocket.close(code=1011)
            except Exception:
                pass
            return

        try:
            await websocket.send_json({
                "type": "done",
                "result": result.model_dump(mode="json"),
            })
            await websocket.close()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    return router
