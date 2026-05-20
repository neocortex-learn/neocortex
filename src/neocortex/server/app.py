"""FastAPI app factory for the Neocortex local server."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from neocortex import __version__
from neocortex.server.security import (
    SecurityMiddleware,
    make_token_dependency,
)


def create_app(token: str, port: int) -> FastAPI:
    """Build the FastAPI app with security wired from day 1 (S0-2 + S0-3).

    Args:
        token: Bearer token clients must present (random per-server start).
        port: The port we're bound to (used for Host header validation).

    Note: no CORS middleware is registered on purpose — browsers' default
    SOP is exactly the boundary we want. Adding CORS would weaken security.
    """
    app = FastAPI(
        title="Neocortex Local Server",
        version=__version__,
        # Docs disabled by default to reduce exposed surface; flip in dev if
        # you need the Swagger UI.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    expected_host = f"127.0.0.1:{port}"
    app.add_middleware(SecurityMiddleware, expected_host=expected_host)

    require_token = make_token_dependency(token)

    @app.get("/healthz")
    async def healthz():
        """Liveness probe — public, no auth (Host check still applies)."""
        return {"status": "ok"}

    @app.get("/api/version", dependencies=[Depends(require_token)])
    async def version():
        """Minimal authenticated endpoint; doubles as security smoke test."""
        return {"version": __version__}

    return app
