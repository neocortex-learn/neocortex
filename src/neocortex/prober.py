"""Socratic Probe — verify skill levels by asking contextual questions about the developer's own code.

Probe types (aligned with Bloom's taxonomy):
- understanding: Edge cases, failure modes, design decisions (Comprehension)
- error_detection: Find errors in AI-generated explanations (Analysis)
- design_tradeoff: Evaluate two approaches, justify preference (Evaluation)
- prediction: Predict behavior of code/system given input (Application)
"""

from __future__ import annotations

import json
from datetime import date

from neocortex.llm.base import LLMProvider
from neocortex.models import Language, Profile

PROBE_TYPES = ("understanding", "error_detection", "design_tradeoff", "prediction")


def _parse_json(text: str) -> dict | None:
    """Best-effort JSON extraction from LLM response."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                return None
        return None


def select_probe_type(confidence: float) -> str:
    """Select probe type based on current confidence level.

    Low confidence → understanding (basics first).
    Medium confidence → error_detection or prediction (verify deeper).
    High confidence → design_tradeoff (expert-level judgment).
    """
    if confidence < 0.3:
        return "understanding"
    if confidence < 0.5:
        return "prediction"
    if confidence < 0.7:
        return "error_detection"
    return "design_tradeoff"


def _build_probe_prompt(
    skill_name: str,
    skill_type: str,
    skill_level: str,
    projects_str: str,
    role: str,
    experience: str,
    probe_type: str,
    lang_inst: str,
) -> str:
    """Build the LLM prompt for each probe type."""
    base_context = f"""\
Developer info:
- Role: {role}
- Experience: {experience} years
- Projects: {projects_str}

Scanned skill: {skill_name} (type: {skill_type}, scan-detected level: {skill_level})"""

    if probe_type == "error_detection":
        return f"""\
You are testing whether a developer can spot errors in AI-generated technical explanations.

{base_context}

Generate a short (3-5 sentence) technical explanation about {skill_name} that contains exactly 1 subtle but real error.
The error should NOT be a typo — it should be a conceptual mistake, a wrong assumption, or an incorrect technical claim
that someone with solid understanding of {skill_name} would catch.

Then generate 1 question asking the developer to identify what's wrong.

Output valid JSON:
{{
  "questions": ["Here is an explanation about {skill_name}:\\n\\n<your flawed explanation>\\n\\nWhat is wrong with this explanation?"],
  "context": "one line about the embedded error (for internal evaluation use)"
}}

{lang_inst}"""

    if probe_type == "design_tradeoff":
        return f"""\
You are testing a developer's ability to evaluate and compare technical approaches.

{base_context}

Present two realistic approaches to a common problem in {skill_name}.
Both approaches should be valid but with different tradeoffs (performance vs readability, consistency vs flexibility, etc.).
Ask the developer which they'd choose and why.

Output valid JSON:
{{
  "questions": ["<describe approach A vs approach B for a specific scenario>\\n\\nWhich approach would you choose, and what are the tradeoffs?"],
  "context": "one line about what the key tradeoff is"
}}

{lang_inst}"""

    if probe_type == "prediction":
        return f"""\
You are testing whether a developer can mentally execute code and predict behavior.

{base_context}

Create a short, realistic code snippet or system scenario involving {skill_name} (3-8 lines of code or a brief config/architecture description).
Ask the developer to predict what happens when it runs, especially in an edge case or non-obvious scenario.

Output valid JSON:
{{
  "questions": ["<code snippet or scenario>\\n\\nWhat happens when this runs? What will the output/behavior be?"],
  "context": "one line about the expected behavior"
}}

{lang_inst}"""

    # Default: understanding (original behavior)
    return f"""\
You are assessing a developer's REAL understanding of a technology.

{base_context}

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


async def generate_probe(
    skill_name: str,
    skill_type: str,
    skill_level: str,
    profile: Profile,
    provider: LLMProvider,
    language: Language = Language.EN,
    probe_type: str = "understanding",
) -> dict:
    """Generate verification questions for a specific skill.

    Returns: {"questions": ["q1", ...], "context": "brief context"}
    """
    lang_inst = "用中文回答。" if language == Language.ZH else "Answer in English."

    project_names = []
    for lang_skill in profile.skills.languages.values():
        project_names.extend(lang_skill.projects)
    projects_str = ", ".join(sorted(set(project_names))[:5]) if project_names else "unknown projects"

    prompt = _build_probe_prompt(
        skill_name, skill_type, skill_level, projects_str,
        role=profile.persona.role.value if profile.persona.role else "unknown",
        experience=profile.persona.experience_years.value if profile.persona.experience_years else "unknown",
        probe_type=probe_type,
        lang_inst=lang_inst,
    )

    messages = [
        {"role": "system", "content": "You are a technical interviewer. Output valid JSON only."},
        {"role": "user", "content": prompt},
    ]

    response = await provider.chat(messages, json_mode=True)
    data = _parse_json(response)
    if data is None:
        return {"questions": [], "context": ""}

    max_q = 1 if probe_type != "understanding" else 2
    return {
        "questions": data.get("questions", [])[:max_q],
        "context": data.get("context", ""),
    }


async def evaluate_response(
    skill_name: str,
    question: str,
    answer: str,
    current_level: str,
    provider: LLMProvider,
    language: Language = Language.EN,
    probe_type: str = "understanding",
) -> dict:
    """Evaluate a developer's answer to a probe question.

    Returns: {"understanding": "none|surface|solid|deep", "confidence_delta": float, "feedback": str}
    """
    lang_inst = "用中文回答。" if language == Language.ZH else "Answer in English."

    type_instructions = {
        "error_detection": (
            "The question asked the developer to find an error in a technical explanation.\n"
            "- 'deep': Correctly identified the error AND explained why it's wrong with technical depth\n"
            "- 'solid': Correctly identified the error\n"
            "- 'surface': Pointed at the right area but didn't pinpoint the actual error\n"
            "- 'none': Failed to find the error or identified a non-error as the problem"
        ),
        "design_tradeoff": (
            "The question asked the developer to compare two technical approaches.\n"
            "- 'deep': Chose an approach with nuanced reasoning, mentioned context-dependent factors\n"
            "- 'solid': Made a reasonable choice with clear tradeoff analysis\n"
            "- 'surface': Chose an approach but reasoning is shallow or one-sided\n"
            "- 'none': No meaningful analysis or completely missed the tradeoffs"
        ),
        "prediction": (
            "The question asked the developer to predict code/system behavior.\n"
            "- 'deep': Correct prediction with explanation of WHY, including edge case awareness\n"
            "- 'solid': Correct prediction with reasonable explanation\n"
            "- 'surface': Partially correct or correct but no explanation\n"
            "- 'none': Wrong prediction"
        ),
    }

    extra = type_instructions.get(probe_type, "")

    prompt = f"""\
Evaluate this developer's answer to a skill verification question.

Skill: {skill_name} (scan-detected level: {current_level})
Question: {question}
Developer's answer: {answer}

{extra}

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
    data = _parse_json(response)
    if data is None:
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


def record_calibration(skill_name: str, predicted: int, actual_understanding: str) -> dict:
    """Record a metacognition calibration entry. Returns {predicted, actual, gap}.

    predicted: user's self-assessment (1-4)
    actual_understanding: probe evaluation result (none/surface/solid/deep)
    gap > 0 means overconfident, gap < 0 means underconfident.
    """
    from neocortex.config import load_gap_progress, save_gap_progress

    actual_scores = {"none": 1, "surface": 2, "solid": 3, "deep": 4}
    actual = actual_scores.get(actual_understanding, 2)
    gap = predicted - actual

    # Try to record in related gap entries
    progress = load_gap_progress()
    for gap_name, entry in progress.items():
        if entry.status in ("learning", "verified") and skill_name.lower() in gap_name.lower():
            entry.calibration_history.append({
                "date": date.today().isoformat(),
                "predicted": predicted,
                "actual": actual,
                "gap": gap,
            })
    save_gap_progress(progress)

    return {"predicted": predicted, "actual": actual, "gap": gap}


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
