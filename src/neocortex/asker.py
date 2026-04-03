"""Interactive Q&A — answer questions with profile context."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path

from neocortex.llm.base import LLMProvider
from neocortex.models import Language, Profile

_CHARS_PER_TOKEN_ESTIMATE = 3
_KNOWLEDGE_CONTEXT_LIMIT = 2000


def _load_knowledge_context(language: Language) -> str:
    """Load INDEX.md as context for Q&A."""
    from neocortex.config import get_notes_dir

    notes_dir = get_notes_dir()
    index_path = notes_dir / "INDEX.md"

    if not index_path.exists():
        return ""

    try:
        content = index_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""

    if not content.strip():
        return ""

    if len(content) > _KNOWLEDGE_CONTEXT_LIMIT:
        content = content[:_KNOWLEDGE_CONTEXT_LIMIT]

    label = "用户的知识库索引" if language == Language.ZH else "User's knowledge base index"
    return f"\n\n{label}:\n{content}"


def _build_system_prompt(
    profile: Profile,
    language: Language,
    knowledge_context: str = "",
) -> str:
    profile_json = json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2)

    lang_inst = "请用中文回答。" if language == Language.ZH else "Answer in English."

    role = profile.persona.role.value if profile.persona.role else "developer"
    exp = profile.persona.experience_years.value if profile.persona.experience_years else ""
    exp_desc = f"（{exp}年经验）" if exp else ""

    prompt = f"""你是一个技术顾问。你面前是一位{role}{exp_desc}，不是初学者。

用户技能画像：
{profile_json}

回答原则：
1. 用对等的语气交流，不要居高临下或过度解释基础概念
2. 对用户已有经验的领域，直接用他做过的项目做类比
3. 重点展开用户的知识盲区（gaps）
4. 给出具体可执行的建议，不要泛泛而谈
5. 如果问题涉及用户的项目，直接用项目名称和细节举例
6. 难度控制在用户当前水平 +1~+2 的范围

{lang_inst}"""

    if knowledge_context:
        prompt += knowledge_context

    return prompt


def _make_slug(text: str) -> str:
    """Turn a question/title into a filesystem-safe slug."""
    safe = "".join(c if c.isalnum() or c in "-_ " else "" for c in text)
    safe = safe.strip().replace(" ", "-").lower()[:60]
    return safe or "insight"


def save_insight(question: str, answer: str, language: Language) -> Path:
    """Save a Q&A exchange as an insight file in insights/ directory."""
    from neocortex.config import get_notes_dir

    notes_dir = get_notes_dir()
    insights_dir = notes_dir / "insights"
    insights_dir.mkdir(parents=True, exist_ok=True)

    slug = _make_slug(question)
    today = date.today().isoformat()
    filename = f"{slug}-{today}.md"
    note_path = insights_dir / filename

    counter = 1
    while note_path.exists():
        counter += 1
        filename = f"{slug}-{today}-{counter}.md"
        note_path = insights_dir / filename

    safe_question = question.replace('"', "'")

    content = f"""---
type: insight
question: "{safe_question}"
date: {today}
source: ask
---

# {question}

{answer}
"""

    fd, tmp_path = tempfile.mkstemp(dir=str(insights_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(note_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return note_path


def save_chat_insights(
    history: list[dict[str, str]],
    language: Language,
) -> list[Path]:
    """Save Q&A pairs from a chat session as individual insight files."""
    paths: list[Path] = []
    pairs: list[tuple[str, str]] = []

    for msg in history:
        if msg["role"] == "user":
            pairs.append((msg["content"], ""))
        elif msg["role"] == "assistant" and pairs and not pairs[-1][1]:
            q, _ = pairs[-1]
            pairs[-1] = (q, msg["content"])

    for question, answer in pairs:
        if not answer:
            continue
        path = save_insight(question, answer, language)
        paths.append(path)

    return paths


async def ask_question(
    question: str,
    profile: Profile,
    provider: LLMProvider,
    language: Language = Language.EN,
) -> str:
    knowledge_context = _load_knowledge_context(language)
    system_prompt = _build_system_prompt(profile, language, knowledge_context)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    return await provider.chat(messages)


class ChatSession:
    """Stateful multi-turn conversation that carries full message history."""

    def __init__(
        self,
        profile: Profile,
        provider: LLMProvider,
        language: Language = Language.EN,
    ) -> None:
        self._provider = provider
        self._language = language
        knowledge_context = _load_knowledge_context(language)
        self._system_message: dict[str, str] = {
            "role": "system",
            "content": _build_system_prompt(profile, language, knowledge_context),
        }
        self._history: list[dict[str, str]] = [self._system_message]
        self._max_context = provider.max_context_tokens()

    @property
    def history(self) -> list[dict[str, str]]:
        return list(self._history)

    async def send(self, message: str) -> str:
        self._history.append({"role": "user", "content": message})
        self._trim_history()
        response = await self._provider.chat(self._history)
        self._history.append({"role": "assistant", "content": response})
        return response

    def _estimate_tokens(self) -> int:
        total_chars = sum(len(m["content"]) for m in self._history)
        return total_chars // _CHARS_PER_TOKEN_ESTIMATE

    def _trim_history(self) -> None:
        budget = int(self._max_context * 0.75)
        if self._estimate_tokens() <= budget:
            return

        non_system = self._history[1:]

        while self._estimate_tokens() > budget and len(non_system) > 1:
            non_system.pop(0)
            self._history = [self._system_message] + non_system
