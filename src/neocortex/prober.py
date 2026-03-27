"""Socratic Probe — verify skill levels by asking contextual questions about the developer's own code."""

from __future__ import annotations

import json
from datetime import date

from neocortex.llm.base import LLMProvider
from neocortex.models import Language, Profile


async def generate_probe(
    skill_name: str,
    skill_type: str,
    skill_level: str,
    profile: Profile,
    provider: LLMProvider,
    language: Language = Language.EN,
) -> dict:
    """Generate 1-2 verification questions for a specific skill.

    Returns: {"questions": ["q1", "q2"], "context": "brief context about what was found"}
    """
    lang_inst = "用中文回答。" if language == Language.ZH else "Answer in English."

    # Build context about the developer's projects
    project_names = []
    for lang_skill in profile.skills.languages.values():
        project_names.extend(lang_skill.projects)
    projects_str = ", ".join(sorted(set(project_names))[:5]) if project_names else "unknown projects"

    prompt = f"""\
You are assessing a developer's REAL understanding of a technology.

Developer info:
- Role: {profile.persona.role.value if profile.persona.role else 'unknown'}
- Experience: {profile.persona.experience_years.value if profile.persona.experience_years else 'unknown'} years
- Projects: {projects_str}

Scanned skill: {skill_name} (type: {skill_type}, scan-detected level: {skill_level})

Generate exactly 2 short verification questions to check if the developer truly understands this technology,
or if it was just AI-generated code they didn't fully comprehend.

Rules:
- Questions should be about UNDERSTANDING, not recall (no "what is the syntax for...")
- Ask about edge cases, failure modes, or design decisions ("what happens when...", "why would you choose X over Y...")
- Keep questions concise (1-2 sentences each)
- Questions should be answerable without looking at code (testing mental model)

Output valid JSON:
{{
  "questions": ["question 1", "question 2"],
  "context": "one line about what was found in their project"
}}

{lang_inst}"""

    messages = [
        {"role": "system", "content": "You are a technical interviewer. Output valid JSON only."},
        {"role": "user", "content": prompt},
    ]

    response = await provider.chat(messages, json_mode=True)

    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(response[start:end])
            except json.JSONDecodeError:
                return {"questions": [], "context": ""}
        else:
            return {"questions": [], "context": ""}

    return {
        "questions": data.get("questions", [])[:2],
        "context": data.get("context", ""),
    }


async def evaluate_response(
    skill_name: str,
    question: str,
    answer: str,
    current_level: str,
    provider: LLMProvider,
    language: Language = Language.EN,
) -> dict:
    """Evaluate a developer's answer to a probe question.

    Returns: {"understanding": "none|surface|solid|deep", "confidence_delta": float, "feedback": str}
    """
    lang_inst = "用中文回答。" if language == Language.ZH else "Answer in English."

    prompt = f"""\
Evaluate this developer's answer to a skill verification question.

Skill: {skill_name} (scan-detected level: {current_level})
Question: {question}
Developer's answer: {answer}

Evaluate their understanding level:
- "none": Cannot answer at all, or answer is completely wrong
- "surface": Knows the basics but lacks depth (e.g., knows what it does but not how/why)
- "solid": Good understanding with accurate details
- "deep": Expert-level insight, mentions edge cases or tradeoffs unprompted

Output valid JSON:
{{
  "understanding": "none|surface|solid|deep",
  "confidence_delta": <float between -0.3 and +0.3>,
  "feedback": "one sentence of constructive feedback for the learner"
}}

Guidelines for confidence_delta:
- "none" on a supposedly advanced skill: -0.3
- "surface" on a proficient skill: -0.1
- "solid" matches the level: +0.1
- "deep" exceeds the level: +0.2 to +0.3
- If the answer is "skip" or empty: 0.0 (no change)

{lang_inst}"""

    messages = [
        {"role": "system", "content": "You are a fair technical evaluator. Output valid JSON only."},
        {"role": "user", "content": prompt},
    ]

    response = await provider.chat(messages, json_mode=True)

    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(response[start:end])
            except json.JSONDecodeError:
                return {"understanding": "surface", "confidence_delta": 0.0, "feedback": ""}
        else:
            return {"understanding": "surface", "confidence_delta": 0.0, "feedback": ""}

    delta = data.get("confidence_delta", 0.0)
    try:
        delta = float(delta)
        delta = max(-0.3, min(0.3, delta))
    except (TypeError, ValueError):
        delta = 0.0

    return {
        "understanding": data.get("understanding", "surface"),
        "confidence_delta": delta,
        "feedback": data.get("feedback", ""),
    }


def update_skill_confidence(
    profile: Profile,
    skill_name: str,
    skill_type: str,
    confidence_delta: float,
) -> float:
    """Update a skill's confidence score. Returns new confidence."""
    skill_map = {
        "language": profile.skills.languages,
        "domain": profile.skills.domains,
        "integration": profile.skills.integrations,
        "architecture": profile.skills.architecture,
    }

    skills = skill_map.get(skill_type, {})
    skill = skills.get(skill_name)
    if skill is None:
        return 0.3

    old = skill.confidence
    skill.confidence = max(0.0, min(1.0, old + confidence_delta))
    skill.last_verified = date.today().isoformat()
    return skill.confidence


def get_low_confidence_skills(profile: Profile, threshold: float = 0.5) -> list[dict]:
    """Find skills with confidence below threshold. Returns list of {name, type, level, confidence}."""
    results: list[dict] = []

    for name, skill in profile.skills.languages.items():
        if skill.confidence < threshold:
            results.append({"name": name, "type": "language", "level": skill.level.value, "confidence": skill.confidence})

    for name, skill in profile.skills.domains.items():
        if skill.confidence < threshold:
            results.append({"name": name, "type": "domain", "level": skill.level.value, "confidence": skill.confidence})

    for name, skill in profile.skills.integrations.items():
        if skill.confidence < threshold:
            results.append({"name": name, "type": "integration", "level": skill.level.value, "confidence": skill.confidence})

    for name, skill in profile.skills.architecture.items():
        if skill.confidence < threshold:
            results.append({"name": name, "type": "architecture", "level": skill.level.value, "confidence": skill.confidence})

    return sorted(results, key=lambda x: x["confidence"])
