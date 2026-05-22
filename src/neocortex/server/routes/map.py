"""GET /api/map — concept map (Mermaid source) for the GUI map panel."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from neocortex.models import ConceptMap
from neocortex.services.visualize import build_concept_map


def make_router(require_token) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["map"])

    @router.get(
        "/map",
        response_model=ConceptMap,
        dependencies=[Depends(require_token)],
    )
    async def map_endpoint(
        domain: str | None = None,
        around: str | None = None,
    ) -> ConceptMap:
        from neocortex.config import get_notes_dir, load_profile

        return build_concept_map(
            notes_dir=get_notes_dir(),
            profile=load_profile(),
            domain=domain,
            around=around,
        )

    return router
