"""Re-translate previously translated clips with updated 3-tier glossary.

Since originals were replaced, re-fetches from source URL or re-translates
the existing Chinese content by asking LLM to apply the new terminology rules.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


TARGET_FILES = [
    "clips/ai-architecture/2026-05-20-llm-powered-autonomous-agents.md",
    "clips/ai-practice/2026-05-20-claude-37-sonnet-and-claude-code.md",
    "clips/career/2026-05-20-what-to-learn-build-and-skip-in-ai-agents-2026.md",
    "clips/engineering/2026-06-03-动画词汇表animation-vocabulary-animationsdev.md",
]

TERM_FIX_PROMPT = """你是一位专业的中文技术文档编辑。请按以下术语规范修订这段中文译文，其他内容不要动。

## 术语规范

### A. 保留英文不译（中文里直接写英文）
API, SDK, PR, CI/CD, Docker, Git, LLM, Token, Benchmark

### B. 翻译成中文，首次出现时括号标注英文（之后只写中文）
AI Agent → AI 智能体（AI Agent）
Context Engineering → 上下文工程（Context Engineering）
Prompt Engineering → 提示词工程（Prompt Engineering）
Fine-tuning → 微调（Fine-tuning）
RAG → 检索增强生成（RAG）
Chain of Thought → 思维链（Chain of Thought）
Embedding → 向量化（Embedding）
Harness → 编排框架（Harness）
Scaffold → 脚手架（Scaffold）
Hallucination → 幻觉（Hallucination）
Alignment → 对齐（Alignment）
Sandbox → 沙箱（Sandbox）
Inference → 推理（Inference）

### C. 直接翻译（中文已通用，不需标注）
Moat → 护城河, Flywheel → 飞轮效应, Latency → 延迟, Throughput → 吞吐量

## 规则
- 如果术语已经按规范处理了（中文+括号英文），不要重复标注
- 只修术语表达方式，不要改动文章内容、结构或措辞
- 直接输出修订后的全文，不要加任何说明"""


async def main():
    dry_run = "--dry-run" in sys.argv

    from neocortex.config import get_notes_dir, load_config
    from neocortex.llm import create_provider

    cfg = load_config()
    provider = create_provider(cfg)
    notes_dir = get_notes_dir()

    for rel_path in TARGET_FILES:
        f = notes_dir / rel_path
        if not f.exists():
            print(f"  SKIP (not found): {rel_path}")
            continue

        text = f.read_text("utf-8")
        m = re.match(r"^(---\n.*?\n---\n?)(.*)", text, re.DOTALL)
        if not m:
            continue

        header = m.group(1)
        body = m.group(2).strip()

        print(f"  Fixing terms: {rel_path}")
        if dry_run:
            continue

        try:
            fixed = await provider.chat([
                {"role": "system", "content": TERM_FIX_PROMPT},
                {"role": "user", "content": body},
            ])
            fixed = fixed.strip()
            if len(fixed) < len(body) * 0.5:
                print("    SKIP: output too short")
                continue
            f.write_text(header + "\n" + fixed, encoding="utf-8")
            print(f"    OK ({len(fixed)} chars)")
        except Exception as e:
            print(f"    ERROR: {e}")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
