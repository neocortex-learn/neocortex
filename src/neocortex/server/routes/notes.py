"""DELETE /api/notes — trash a note + reverse concept refs.

POST body: { "path": "<absolute or vault-relative .md path>" }
Returns:    { deleted, trashed, reversed_concepts: [...], indexed_removed }
HTTP codes:
    200 ok
    400 bad path (escapes vault / wrong suffix)
    404 not found
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field


class DeleteNoteRequest(BaseModel):
    """Body for DELETE /api/notes (use POST since some clients dislike DELETE bodies)."""
    path: str = Field(..., min_length=1, description="Absolute or vault-relative .md path")


class DeleteNoteResponse(BaseModel):
    deleted: str
    trashed: bool
    reversed_concepts: list[str]
    indexed_removed: int


def make_router(require_token) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["notes"])

    @router.post(
        "/notes/delete",
        response_model=DeleteNoteResponse,
        dependencies=[Depends(require_token)],
    )
    async def delete_endpoint(req: DeleteNoteRequest) -> DeleteNoteResponse:
        from neocortex.config import get_data_dir, get_notes_dir
        from neocortex.services.notes import delete_note

        notes_dir = get_notes_dir()
        # Accept absolute and vault-relative paths transparently
        candidate = Path(req.path).expanduser()
        if not candidate.is_absolute():
            candidate = notes_dir / candidate

        try:
            report = delete_note(
                notes_dir,
                candidate,
                db_path=get_data_dir() / "neocortex.sqlite",
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except PermissionError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        return DeleteNoteResponse(**report)

    return router
