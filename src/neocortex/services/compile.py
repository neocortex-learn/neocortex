"""Compile service: console-free wrapper around ``compiler.compile_all``.

Wraps the ``kb compile`` engine for HTTP / GUI consumption. The CLI keeps
its own Rich progress rendering (cmd_compile.compile); this service is the
plain-data path the Mac client hits. It reproduces the CLI's note-collection
filter and activity-log side effect so both entrances stay behaviourally
identical.

``verify`` (fidelity check after compile) is CLI-only for now — it adds
minutes of LLM calls and the GUI has no surface to render the report yet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from neocortex.compiler import collect_compilable_notes
from neocortex.models import AppConfig, CompileResult, Language, Profile


async def compile_notes(
    *,
    notes_dir: Path,
    cfg: AppConfig,
    profile: Profile,
    lang: Language,
    force: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
) -> CompileResult:
    """Run incremental concept compilation and return the engine result.

    Raises ValueError when the LLM provider is unconfigured — callers turn
    that into a 400 (the job never starts, so no failed-state noise).
    """
    from neocortex.compiler import compile_all
    from neocortex.config import append_log
    from neocortex.llm import create_provider

    if not (cfg.provider and cfg.api_key):
        raise ValueError("LLM provider / api_key 未配置；运行 neocortex profile config")

    provider = create_provider(cfg)

    if not collect_compilable_notes(notes_dir):
        return CompileResult()

    result = await compile_all(
        notes_dir, profile, provider, lang,
        on_progress=on_progress,
        force=force,
    )

    if result.notes_processed > 0:
        append_log(
            "compile",
            f"{result.notes_processed} notes, "
            f"{result.concepts_created + result.concepts_updated} concepts",
        )

    return result
