"""POST /api/compile + GET /api/compile/status — concept compilation for GUI.

Compilation is a minutes-long LLM batch, so the HTTP surface is
start-then-poll instead of a blocking request: POST kicks off (or reports)
the single in-flight job, GET returns a snapshot. Job state lives in the
router closure — one compile at a time per server process, mirroring the
single-writer assumption the compiler already makes about vault files.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from neocortex.models import CompileJobStatus, CompileResult


class CompileRequest(BaseModel):
    force: bool = False


class _CompileJob:
    """Mutable state for the single in-flight compile job."""

    def __init__(self) -> None:
        self.task: asyncio.Task | None = None
        self.status = CompileJobStatus()

    def snapshot(self, *, accepted: bool = True) -> CompileJobStatus:
        return self.status.model_copy(update={"accepted": accepted})

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()


def make_router(require_token) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["compile"])
    job = _CompileJob()

    async def _run(force: bool) -> None:
        from neocortex.config import get_notes_dir, load_config, load_profile
        from neocortex.services.compile import compile_notes

        cfg = load_config()

        def on_progress(current: int, total: int) -> None:
            job.status.current = current
            job.status.total = total

        try:
            result: CompileResult = await compile_notes(
                notes_dir=get_notes_dir(),
                cfg=cfg,
                profile=load_profile(),
                lang=cfg.output_settings.language,
                force=force,
                on_progress=on_progress,
            )
            job.status.result = result
            job.status.state = "done"
        except Exception as exc:  # surfaced via /status, never silent
            job.status.error = f"{type(exc).__name__}: {exc}"
            job.status.state = "failed"
        finally:
            job.status.finished_at = datetime.now().isoformat(timespec="seconds")

    @router.post(
        "/compile",
        response_model=CompileJobStatus,
        dependencies=[Depends(require_token)],
    )
    async def start_compile(body: CompileRequest | None = None) -> CompileJobStatus:
        from neocortex.config import load_config

        if job.running:
            return job.snapshot(accepted=False)

        force = bool(body and body.force)

        # Fail fast on missing LLM config — a 400 now beats a failed job later.
        cfg = load_config()
        if not (cfg.provider and cfg.api_key):
            raise HTTPException(
                status_code=400,
                detail="LLM provider / api_key 未配置；运行 neocortex profile config",
            )

        job.status = CompileJobStatus(
            state="running",
            force=force,
            started_at=datetime.now().isoformat(timespec="seconds"),
        )
        job.task = asyncio.create_task(_run(force))
        return job.snapshot()

    @router.get(
        "/compile/status",
        response_model=CompileJobStatus,
        dependencies=[Depends(require_token)],
    )
    async def compile_status() -> CompileJobStatus:
        return job.snapshot()

    return router
