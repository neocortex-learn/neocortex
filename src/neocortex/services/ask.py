"""Ask service: single-turn Q&A with auto-evaluate + insight save.

Wraps ``asker.ask_question`` for HTTP / GUI consumption. The CLI keeps its
own interactive ``chat`` loop (cmd_knowledge.ask); this service is the
one-shot path the Mac client + future iOS hit.

Auto-save (Query 反写, CLAUDE.md):
    answer → evaluate_insight_value → if valuable, save_insight.
    Failures in the evaluator are non-fatal (treated as "not worth saving").
"""

from __future__ import annotations

import time
from pathlib import Path

from neocortex.models import AppConfig, AskResult, Language, Profile


async def ask_question(
    question: str,
    *,
    notes_dir: Path,
    cfg: AppConfig,
    profile: Profile,
    lang: Language,
) -> AskResult:
    from neocortex.asker import ask_question as _ask
    from neocortex.asker import evaluate_insight_value, save_insight
    from neocortex.llm import create_provider

    started = time.monotonic()

    if not (cfg.provider and cfg.api_key):
        return AskResult(
            question=question, answer="",
            aborted=True,
            abort_reason="LLM provider / api_key 未配置；运行 neocortex profile config",
        )

    try:
        provider = create_provider(cfg)
    except Exception as exc:
        return AskResult(
            question=question, answer="",
            aborted=True,
            abort_reason=f"create_provider 失败: {exc}",
        )

    try:
        answer = await _ask(question, profile, provider, language=lang)
    except Exception as exc:
        return AskResult(
            question=question, answer="",
            aborted=True,
            abort_reason=f"LLM 调用失败: {exc}",
        )

    saved_rel: str | None = None
    warnings: list[str] = []
    try:
        if await evaluate_insight_value(question, answer, provider):
            path = save_insight(question, answer, lang)
            if path.is_relative_to(notes_dir):
                saved_rel = str(path.relative_to(notes_dir))
            else:
                saved_rel = str(path)
    except Exception as exc:
        # Evaluator / save failure shouldn't blow up the answer the user
        # already has — degrade to "not saved" but surface it via warnings
        # so the GUI can tell "evaluated as not valuable" from "eval broke".
        from neocortex.i18n import t

        saved_rel = None
        warnings.append(t("insight_evaluate_failed", lang, error=str(exc) or exc.__class__.__name__))

    # Activity log so GUI-triggered asks appear in the timeline.
    try:
        from neocortex.config import append_log
        suffix = " → saved as insight" if saved_rel else ""
        append_log("ask", f"{question[:80]}{suffix}")
    except Exception:
        pass

    return AskResult(
        question=question,
        answer=answer,
        saved_as_insight=saved_rel,
        elapsed_seconds=round(time.monotonic() - started, 2),
        warnings=warnings,
    )
