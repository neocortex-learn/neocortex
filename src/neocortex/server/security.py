"""Security middleware + dependency for the local HTTP server.

Per CLIENT_PROPOSAL.md §5.4. Threats considered:
    - Random browser page on the user's machine probing 127.0.0.1
    - DNS rebinding attack (malicious domain → 127.0.0.1)
    - Form-based CSRF (mutating endpoints triggered cross-origin)

Mitigations (all stacked, defense in depth):
    1. Bearer Token (per-server random, 0600 file)
    2. Host header strict match (defeats DNS rebinding)
    3. Origin header whitelist (defeats most cross-origin probes)
    4. Content-Type=application/json on mutating methods (defeats form CSRF)
    5. No CORS headers set (browsers SOP-block by default)
"""

from __future__ import annotations

import secrets
from typing import Iterable

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


PUBLIC_PATHS: frozenset[str] = frozenset(["/healthz"])

ALLOWED_ORIGINS: frozenset[str] = frozenset([
    "null",                  # local file:// origin
    "tauri://localhost",     # future Tauri client
    # SwiftUI's URLSession typically sends no Origin header → also allowed
    # (the absent-Origin branch is handled below).
])

MUTATING_METHODS: frozenset[str] = frozenset(["POST", "PUT", "PATCH", "DELETE"])


class SecurityMiddleware(BaseHTTPMiddleware):
    """Bundle Host / Origin / Content-Type checks into one middleware.

    The Bearer Token check is a FastAPI dependency (``require_token``) so it
    can be selectively applied per-route; everything else applies globally.
    """

    def __init__(self, app, expected_host: str):
        super().__init__(app)
        # expected_host is "127.0.0.1:<port>" — set at app construction time.
        self._expected_hosts = frozenset([
            expected_host,
            expected_host.replace("127.0.0.1", "localhost"),
        ])

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # /healthz is the only path that bypasses all auth; it still goes
        # through host/origin checks to detect DNS rebinding probes.
        host = request.headers.get("host", "")
        if host not in self._expected_hosts:
            return _json_error(400, f"unexpected Host header: {host!r}")

        origin = request.headers.get("origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            return _json_error(403, f"origin {origin!r} not allowed")

        if request.method in MUTATING_METHODS and path not in PUBLIC_PATHS:
            ctype = request.headers.get("content-type", "").lower().split(";")[0].strip()
            if ctype != "application/json":
                return _json_error(
                    415, "Content-Type must be application/json for mutating requests"
                )

        # Important: NEVER set Access-Control-Allow-Origin. Browsers will block
        # cross-origin requests by SOP — that's the desired behaviour.
        return await call_next(request)


def _json_error(code: int, detail: str) -> Response:
    """Build a JSON error response without exposing internals."""
    import json
    body = json.dumps({"detail": detail}).encode("utf-8")
    return Response(content=body, status_code=code, media_type="application/json")


async def validate_ws_handshake(
    websocket,
    *,
    expected_token: str,
    expected_host: str,
) -> bool:
    """Run the same checks SecurityMiddleware does, but for WebSocket scope.

    Starlette's BaseHTTPMiddleware only sees ``http`` scope, so every WS
    endpoint must do its own host/origin/token validation. Centralising it
    here keeps the security model consistent — if we later add an allowed
    origin or change token storage, both paths track together instead of
    drifting.

    Returns True when the handshake passed and the caller should ``accept()``.
    Returns False after closing the socket with the appropriate code so the
    caller just returns.
    """
    expected_hosts = {
        expected_host,
        expected_host.replace("127.0.0.1", "localhost"),
    }

    host = websocket.headers.get("host", "")
    if host not in expected_hosts:
        await websocket.close(code=1008, reason="bad host")
        return False

    origin = websocket.headers.get("origin")
    if origin is not None and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008, reason="bad origin")
        return False

    # Token: prefer Authorization header (native clients); fall back to
    # ?token= query for browsers (which can't set custom WS headers).
    auth = websocket.headers.get("authorization", "")
    token: str | None = None
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    else:
        token = websocket.query_params.get("token")

    if not token or not secrets.compare_digest(token, expected_token):
        await websocket.close(code=1008, reason="bad token")
        return False

    return True


def make_token_dependency(expected_token: str):
    """Build a FastAPI dependency that validates Bearer token.

    Use ``Depends(require_token)`` on every protected endpoint. We return a
    factory so the app can capture its specific token without globals.
    """

    async def require_token(request: Request) -> None:
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing or malformed Authorization header",
            )
        provided = auth.split(" ", 1)[1].strip()
        if not secrets.compare_digest(provided, expected_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid token",
            )

    return require_token
