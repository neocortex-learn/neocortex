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

# ── Gap synonym table ──
# Maps variant names to a canonical form. Covers common LLM output variations.
# Add new entries as they're discovered in real usage.

_GAP_SYNONYMS: dict[str, str] = {
    # Testing
    "unit_testing": "testing",
    "unit_test": "testing",
    "test": "testing",
    "pytest": "testing",
    "jest": "testing",
    "mocha": "testing",
    "testing_framework": "testing",
    "test_coverage": "test_coverage",
    "code_coverage": "test_coverage",
    "coverage": "test_coverage",
    "pytest_fixtures": "pytest_fixtures",
    "test_fixtures": "pytest_fixtures",
    # CI/CD
    "ci": "ci_cd",
    "cd": "ci_cd",
    "ci_cd": "ci_cd",
    "continuous_integration": "ci_cd",
    "continuous_deployment": "ci_cd",
    "github_actions": "ci_cd",
    # Docker / Containers
    "docker": "containerization",
    "docker_compose": "docker_compose",
    "containers": "containerization",
    "containerization": "containerization",
    "kubernetes": "kubernetes",
    "k8s": "kubernetes",
    # Databases
    "sql": "sql",
    "sql_query": "sql",
    "query_optimization": "query_optimization",
    "database_optimization": "query_optimization",
    "indexing": "query_optimization",
    "database_indexing": "query_optimization",
    # Security
    "security": "security",
    "web_security": "security",
    "authentication": "authentication",
    "auth": "authentication",
    "oauth": "authentication",
    "authorization": "authorization",
    # API
    "api_design": "api_design",
    "rest_api": "api_design",
    "api": "api_design",
    # Performance
    "performance": "performance",
    "optimization": "performance",
    "caching": "caching",
    "cache": "caching",
    "redis": "caching",
    # Architecture
    "system_design": "system_design",
    "architecture": "system_design",
    "design_patterns": "design_patterns",
    "patterns": "design_patterns",
    # Monitoring
    "monitoring": "monitoring",
    "observability": "monitoring",
    "logging": "monitoring",
    "error_handling": "error_handling",
    "exception_handling": "error_handling",
}


def normalize_gap_name(gap: str) -> str:
    """Normalize a gap name using synonym table + lowercase/snake_case."""
    normalized = gap.strip().lower().replace("-", "_").replace(" ", "_")
    return _GAP_SYNONYMS.get(normalized, normalized)


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
            lv_a = a[key].last_verified
            lv_b = b[key].last_verified
            result[key] = LanguageSkill(
                level=_higher_level(a[key].level, b[key].level),
                confidence=max(a[key].confidence, b[key].confidence),
                last_verified=max(lv_a, lv_b) if lv_a and lv_b else (lv_a or lv_b),
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


def _normalize_gaps(gaps: list[str]) -> list[str]:
    """Deduplicate gaps after applying synonym normalization."""
    return list(dict.fromkeys(normalize_gap_name(g) for g in gaps if g))


def _merge_domains(
    a: dict[str, DomainSkill], b: dict[str, DomainSkill]
) -> dict[str, DomainSkill]:
    result: dict[str, DomainSkill] = {}
    all_keys = set(a) | set(b)
    for key in all_keys:
        if key in a and key in b:
            merged_gaps = _merge_unique(a[key].gaps, b[key].gaps)
            lv_a = a[key].last_verified
            lv_b = b[key].last_verified
            result[key] = DomainSkill(
                level=_higher_level(a[key].level, b[key].level),
                confidence=max(a[key].confidence, b[key].confidence),
                last_verified=max(lv_a, lv_b) if lv_a and lv_b else (lv_a or lv_b),
                evidence=_merge_unique(a[key].evidence, b[key].evidence),
                gaps=_normalize_gaps(merged_gaps),
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
            merged_gaps = _merge_unique(a[key].gaps, b[key].gaps)
            lv_a = a[key].last_verified
            lv_b = b[key].last_verified
            result[key] = IntegrationSkill(
                level=_higher_level(a[key].level, b[key].level),
                confidence=max(a[key].confidence, b[key].confidence),
                last_verified=max(lv_a, lv_b) if lv_a and lv_b else (lv_a or lv_b),
                providers=_merge_unique(a[key].providers, b[key].providers),
                gaps=_normalize_gaps(merged_gaps),
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
            lv_a = a[key].last_verified
            lv_b = b[key].last_verified
            result[key] = ArchitectureSkill(
                level=_higher_level(a[key].level, b[key].level),
                confidence=max(a[key].confidence, b[key].confidence),
                last_verified=max(lv_a, lv_b) if lv_a and lv_b else (lv_a or lv_b),
                patterns=_merge_unique(a[key].patterns, b[key].patterns),
                evidence=_merge_unique(a[key].evidence, b[key].evidence),
            )
        elif key in a:
            result[key] = a[key].model_copy()
        else:
            result[key] = b[key].model_copy()
    return result
