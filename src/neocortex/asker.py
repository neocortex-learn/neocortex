"""Interactive Q&A — answer questions with profile context."""

from __future__ import annotations

import json

from neocortex.llm.base import LLMProvider
from neocortex.models import Language, Profile

_CHARS_PER_TOKEN_ESTIMATE = 3


def _build_system_prompt(profile: Profile, language: Language) -> str:
    profile_json = json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2)

    lang_inst = "请用中文回答。" if language == Language.ZH else "Answer in English."

    return f"""你是一个了解学生的私人技术导师。

学生画像：
{profile_json}

回答原则：
1. 跳过学生已经精通的基础概念，不要浪费篇幅
2. 对学生已有经验的领域，用他做过的项目做类比
3. 重点展开学生的知识盲区（gaps）
4. 给出具体可执行的建议，不要泛泛而谈
5. 如果问题涉及学生的项目，直接用项目名称和细节举例
6. 难度控制在学生当前水平 +1~+2 的范围

{lang_inst}"""


async def ask_question(
    question: str,
    profile: Profile,
    provider: LLMProvider,
    language: Language = Language.EN,
) -> str:
    system_prompt = _build_system_prompt(profile, language)

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
        self._system_message: dict[str, str] = {
            "role": "system",
            "content": _build_system_prompt(profile, language),
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
