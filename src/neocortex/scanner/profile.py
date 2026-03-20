"""Skill profile management — merge multiple skill profiles."""

from __future__ import annotations

from neocortex.models import (
    ArchitectureSkill,
    DomainSkill,
    IntegrationSkill,
    LanguageSkill,
    SkillLevel,
    Skills,
)

LEVEL_ORDER: dict[SkillLevel, int] = {
    SkillLevel.BEGINNER: 0,
    SkillLevel.PROFICIENT: 1,
    SkillLevel.ADVANCED: 2,
    SkillLevel.EXPERT: 3,
}


def _higher_level(a: SkillLevel, b: SkillLevel) -> SkillLevel:
    return a if LEVEL_ORDER[a] >= LEVEL_ORDER[b] else b


def _merge_unique(a: list[str], b: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in a + b:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def merge_profiles(existing: Skills, new: Skills) -> Skills:
    """Merge two skill profiles.

    Strategy:
    - Same skill: take the higher level
    - lines: accumulate
    - evidence/frameworks/patterns/providers/projects: merge and deduplicate
    - gaps: union (different projects expose different gaps, keep all)
    """
    languages = _merge_languages(existing.languages, new.languages)
    domains = _merge_domains(existing.domains, new.domains)
    integrations = _merge_integrations(existing.integrations, new.integrations)
    architecture = _merge_architecture(existing.architecture, new.architecture)

    return Skills(
        languages=languages,
        domains=domains,
        integrations=integrations,
        architecture=architecture,
    )


def _merge_languages(
    a: dict[str, LanguageSkill], b: dict[str, LanguageSkill]
) -> dict[str, LanguageSkill]:
    result: dict[str, LanguageSkill] = {}
    all_keys = set(a) | set(b)
    for key in all_keys:
        if key in a and key in b:
            result[key] = LanguageSkill(
                level=_higher_level(a[key].level, b[key].level),
                lines=a[key].lines + b[key].lines,
                frameworks=_merge_unique(a[key].frameworks, b[key].frameworks),
                patterns=_merge_unique(a[key].patterns, b[key].patterns),
                projects=_merge_unique(a[key].projects, b[key].projects),
            )
        elif key in a:
            result[key] = a[key].model_copy()
        else:
            result[key] = b[key].model_copy()
    return result


def _merge_domains(
    a: dict[str, DomainSkill], b: dict[str, DomainSkill]
) -> dict[str, DomainSkill]:
    result: dict[str, DomainSkill] = {}
    all_keys = set(a) | set(b)
    for key in all_keys:
        if key in a and key in b:
            result[key] = DomainSkill(
                level=_higher_level(a[key].level, b[key].level),
                evidence=_merge_unique(a[key].evidence, b[key].evidence),
                gaps=_merge_unique(a[key].gaps, b[key].gaps),
            )
        elif key in a:
            result[key] = a[key].model_copy()
        else:
            result[key] = b[key].model_copy()
    return result


def _merge_integrations(
    a: dict[str, IntegrationSkill], b: dict[str, IntegrationSkill]
) -> dict[str, IntegrationSkill]:
    result: dict[str, IntegrationSkill] = {}
    all_keys = set(a) | set(b)
    for key in all_keys:
        if key in a and key in b:
            result[key] = IntegrationSkill(
                level=_higher_level(a[key].level, b[key].level),
                providers=_merge_unique(a[key].providers, b[key].providers),
                gaps=_merge_unique(a[key].gaps, b[key].gaps),
            )
        elif key in a:
            result[key] = a[key].model_copy()
        else:
            result[key] = b[key].model_copy()
    return result


def _merge_architecture(
    a: dict[str, ArchitectureSkill], b: dict[str, ArchitectureSkill]
) -> dict[str, ArchitectureSkill]:
    result: dict[str, ArchitectureSkill] = {}
    all_keys = set(a) | set(b)
    for key in all_keys:
        if key in a and key in b:
            result[key] = ArchitectureSkill(
                level=_higher_level(a[key].level, b[key].level),
                patterns=_merge_unique(a[key].patterns, b[key].patterns),
                evidence=_merge_unique(a[key].evidence, b[key].evidence),
            )
        elif key in a:
            result[key] = a[key].model_copy()
        else:
            result[key] = b[key].model_copy()
    return result
