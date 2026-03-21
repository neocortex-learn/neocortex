"""LLM skill analyzer — send project summary to LLM for structured skill assessment."""

from __future__ import annotations

import json
import sys

from neocortex.llm.base import LLMProvider
from neocortex.models import (
    ArchitectureSkill,
    DomainSkill,
    IntegrationSkill,
    LanguageSkill,
    ProjectInfo,
    SkillLevel,
    Skills,
)

SKILL_LEVELS = {
    "beginner": SkillLevel.BEGINNER,
    "proficient": SkillLevel.PROFICIENT,
    "advanced": SkillLevel.ADVANCED,
    "expert": SkillLevel.EXPERT,
}

_NOISE_KEYS = frozenset({
    "none", "general", "other", "misc", "unknown", "n/a", "na", "",
    "backend_api", "rest_api", "backend", "frontend", "api",
    "build_tools", "video_codecs", "ui_component",
})


def _normalize_key(key: str) -> str:
    """Normalize a skill key to lowercase, stripped."""
    return key.strip().lower()


def _is_noise(key: str) -> bool:
    """Check if a key is meaningless noise."""
    return _normalize_key(key) in _NOISE_KEYS


async def analyze_project(
    project_info: ProjectInfo,
    key_files: list[dict],
    provider: LLMProvider,
) -> Skills:
    """Send project summary to LLM and get structured skill assessment."""
    prompt = build_analysis_prompt(project_info, key_files)
    messages = [{"role": "user", "content": prompt}]
    response = await provider.chat(messages, json_mode=True)
    try:
        skills = _parse_skills(response)
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError, ValueError) as e:
        print(f"Warning: Failed to parse LLM response: {e}", file=sys.stderr)
        return Skills()

    for lang_name, actual_lines in project_info.languages.items():
        lang_key = lang_name.lower()
        for skill_key, skill in skills.languages.items():
            if skill_key.lower() == lang_key:
                skill.lines = actual_lines
                break

    return skills


def build_analysis_prompt(project_info: ProjectInfo, key_files: list[dict]) -> str:
    """Build the analysis prompt to send to LLM."""
    lang_summary = "\n".join(
        f"  - {lang}: {lines} lines"
        for lang, lines in sorted(project_info.languages.items(), key=lambda x: -x[1])
    )

    config_summary = ", ".join(project_info.config_files) if project_info.config_files else "none"
    framework_summary = ", ".join(project_info.frameworks) if project_info.frameworks else "none"
    signal_summary = ", ".join(project_info.architecture_signals) if project_info.architecture_signals else "none"

    file_summaries: list[str] = []
    for kf in key_files[:20]:
        content_preview = kf["content"][:500]
        file_summaries.append(
            f"--- {kf['path']} ({kf['type']}) ---\n{content_preview}"
        )
    files_text = "\n\n".join(file_summaries) if file_summaries else "none"

    return f"""你是一个技术能力评估专家。根据以下项目摘要，评估开发者的技能水平。

项目名称：{project_info.name}
项目路径：{project_info.path}

语言与代码量：
{lang_summary}

配置文件：{config_summary}
框架/工具：{framework_summary}
架构信号：{signal_summary}

关键文件摘要：
{files_text}

请输出 JSON 格式的技能评估，严格遵循以下结构：

{{
  "languages": {{
    "<语言名>": {{
      "level": "beginner|proficient|advanced|expert",
      "lines": <行数>,
      "frameworks": ["框架1", "框架2"],
      "patterns": ["用到的模式，如 MVC, REST, async"],
      "projects": ["{project_info.name}"]
    }}
  }},
  "domains": {{
    "<技术领域，如 web_backend, payment, realtime>": {{
      "level": "beginner|proficient|advanced|expert",
      "evidence": ["具体证据"],
      "gaps": ["可能的知识盲区"]
    }}
  }},
  "integrations": {{
    "<集成名，如 stripe, aws_s3, redis>": {{
      "level": "beginner|proficient|advanced|expert",
      "providers": ["具体提供商"],
      "gaps": ["可能的盲区"]
    }}
  }},
  "architecture": {{
    "<架构模式，如 microservices, monolith, event_driven>": {{
      "level": "beginner|proficient|advanced|expert",
      "patterns": ["具体模式"],
      "evidence": ["具体证据"]
    }}
  }}
}}

对每项技能评估等级：
- beginner: 简单使用，无复杂场景
- proficient: 有实际项目经验，覆盖常见场景
- advanced: 深度使用，处理过复杂问题
- expert: 大规模生产环境，多项目验证

命名规范：
- 所有 key 使用小写下划线格式
- 用简短的通用名称（如 aws, redis, stripe），不要用冗长描述
- 不要使用 none, general, other, unknown 等无意义的 key
- 知名缩写保持简短：aws（不要 amazon_web_services）, gcp, spa（不要 spa_single_page_application）

重要：也要指出可能的知识盲区（gaps），基于项目中缺失的最佳实践。
只输出 JSON，不要输出其他内容。"""


def _parse_skills(response: str) -> Skills:
    """Parse LLM JSON response into Skills model."""
    text = response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1 if lines[0].strip().startswith("```") else 0
        end = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() == "```":
                end = i
                break
        text = "\n".join(lines[start:end])

    data = json.loads(text)

    languages: dict[str, LanguageSkill] = {}
    for lang_name, lang_data in data.get("languages", {}).items():
        languages[lang_name] = LanguageSkill(
            level=SKILL_LEVELS.get(lang_data.get("level", "beginner"), SkillLevel.BEGINNER),
            lines=lang_data.get("lines", 0),
            frameworks=lang_data.get("frameworks", []),
            patterns=lang_data.get("patterns", []),
            projects=lang_data.get("projects", []),
        )

    from neocortex.scanner.profile import normalize_gap_name

    domains: dict[str, DomainSkill] = {}
    for domain_name, domain_data in data.get("domains", {}).items():
        key = _normalize_key(domain_name)
        if _is_noise(key):
            continue
        raw_gaps = domain_data.get("gaps", [])
        normalized_gaps = list(dict.fromkeys(normalize_gap_name(g) for g in raw_gaps if g))
        domains[key] = DomainSkill(
            level=SKILL_LEVELS.get(domain_data.get("level", "beginner"), SkillLevel.BEGINNER),
            evidence=domain_data.get("evidence", []),
            gaps=normalized_gaps,
        )

    integrations: dict[str, IntegrationSkill] = {}
    for int_name, int_data in data.get("integrations", {}).items():
        key = _normalize_key(int_name)
        if _is_noise(key):
            continue
        raw_gaps = int_data.get("gaps", [])
        normalized_gaps = list(dict.fromkeys(normalize_gap_name(g) for g in raw_gaps if g))
        integrations[key] = IntegrationSkill(
            level=SKILL_LEVELS.get(int_data.get("level", "beginner"), SkillLevel.BEGINNER),
            providers=int_data.get("providers", []),
            gaps=normalized_gaps,
        )

    architecture: dict[str, ArchitectureSkill] = {}
    for arch_name, arch_data in data.get("architecture", {}).items():
        key = _normalize_key(arch_name)
        if _is_noise(key):
            continue
        architecture[key] = ArchitectureSkill(
            level=SKILL_LEVELS.get(arch_data.get("level", "beginner"), SkillLevel.BEGINNER),
            patterns=arch_data.get("patterns", []),
            evidence=arch_data.get("evidence", []),
        )

    return Skills(
        languages=languages,
        domains=domains,
        integrations=integrations,
        architecture=architecture,
    )
