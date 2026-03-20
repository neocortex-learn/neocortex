"""Interactive Q&A — answer questions with profile context."""

from __future__ import annotations

import json

from neocortex.llm.base import LLMProvider
from neocortex.models import Language, Profile


async def ask_question(
    question: str,
    profile: Profile,
    provider: LLMProvider,
    language: Language = Language.EN,
) -> str:
    profile_json = json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2)

    lang_inst = "请用中文回答。" if language == Language.ZH else "Answer in English."

    system_prompt = f"""你是一个了解学生的私人技术导师。

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

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    return await provider.chat(messages)
