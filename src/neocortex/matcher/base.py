"""Base matching logic — score opportunities against skill profile."""

from __future__ import annotations

from neocortex.models import Opportunity, Profile, SkillLevel

_LEVEL_WEIGHTS = {
    SkillLevel.BEGINNER: 0.25,
    SkillLevel.PROFICIENT: 0.5,
    SkillLevel.ADVANCED: 0.75,
    SkillLevel.EXPERT: 1.0,
}


def build_skill_vector(profile: Profile) -> dict[str, float]:
    """Build a weighted skill vector from the profile."""
    vector: dict[str, float] = {}
    for name, skill in profile.skills.languages.items():
        vector[name.lower()] = _LEVEL_WEIGHTS.get(skill.level, 0.25)
        for fw in skill.frameworks:
            vector[fw.lower()] = _LEVEL_WEIGHTS.get(skill.level, 0.25) * 0.8
    for name, skill in profile.skills.domains.items():
        vector[name.lower()] = _LEVEL_WEIGHTS.get(skill.level, 0.25)
    for name, skill in profile.skills.integrations.items():
        vector[name.lower()] = _LEVEL_WEIGHTS.get(skill.level, 0.25)
    for name, skill in profile.skills.architecture.items():
        vector[name.lower()] = _LEVEL_WEIGHTS.get(skill.level, 0.25)
    return vector


def score_opportunity(skill_vector: dict[str, float], required: list[str]) -> tuple[float, list[str], list[str]]:
    """Score an opportunity against skill vector. Returns (score, matched, missing)."""
    if not required:
        return 0.0, [], []
    matched = []
    missing = []
    total_weight = 0.0
    matched_weight = 0.0
    for req in required:
        req_lower = req.lower()
        total_weight += 1.0
        if req_lower in skill_vector:
            matched.append(req)
            matched_weight += skill_vector[req_lower]
        else:
            missing.append(req)
    score = matched_weight / total_weight if total_weight > 0 else 0.0
    return round(score, 2), matched, missing
