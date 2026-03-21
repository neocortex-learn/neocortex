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


def _normalize_dict_keys(d: dict) -> dict:
    """Normalize dictionary keys to lowercase, merging data from duplicate keys."""
    result: dict = {}
    for key, value in d.items():
        normalized = key.strip().lower()
        if normalized in result:
            existing = result[normalized]
            # Merge both entries instead of discarding one
            if hasattr(existing, "level") and hasattr(value, "level"):
                higher = _higher_level(existing.level, value.level)
                # Merge list fields from both entries
                merged = existing.model_copy()
                merged.level = higher
                for field_name in ("evidence", "gaps", "frameworks", "patterns",
                                   "providers", "projects"):
                    if hasattr(merged, field_name) and hasattr(value, field_name):
                        existing_list = getattr(merged, field_name)
                        new_list = getattr(value, field_name)
                        setattr(merged, field_name, _merge_unique(existing_list, new_list))
                if hasattr(merged, "lines") and hasattr(value, "lines"):
                    merged.lines = max(existing.lines, value.lines)
                result[normalized] = merged
            else:
                result[normalized] = value
        else:
            result[normalized] = value
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
    domains = _merge_domains(
        _normalize_dict_keys(existing.domains),
        _normalize_dict_keys(new.domains),
    )
    integrations = _merge_integrations(
        _normalize_dict_keys(existing.integrations),
        _normalize_dict_keys(new.integrations),
    )
    architecture = _merge_architecture(
        _normalize_dict_keys(existing.architecture),
        _normalize_dict_keys(new.architecture),
    )

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
