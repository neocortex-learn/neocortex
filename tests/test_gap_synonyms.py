"""Tests for gap semantic deduplication via synonym table."""

from __future__ import annotations

from neocortex.models import DomainSkill, IntegrationSkill, Skills, SkillLevel
from neocortex.scanner.profile import normalize_gap_name, merge_profiles


class TestNormalizeGapName:
    def test_exact_synonym(self):
        assert normalize_gap_name("unit_testing") == "testing"
        assert normalize_gap_name("pytest") == "testing"
        assert normalize_gap_name("unit_test") == "testing"

    def test_preserves_canonical(self):
        assert normalize_gap_name("testing") == "testing"
        assert normalize_gap_name("test_coverage") == "test_coverage"

    def test_unknown_passes_through(self):
        assert normalize_gap_name("quantum_computing") == "quantum_computing"

    def test_case_insensitive(self):
        assert normalize_gap_name("PYTEST") == "testing"
        assert normalize_gap_name("Unit_Testing") == "testing"

    def test_strips_whitespace(self):
        assert normalize_gap_name("  pytest  ") == "testing"

    def test_hyphens_converted(self):
        assert normalize_gap_name("unit-testing") == "testing"
        assert normalize_gap_name("ci-cd") == "ci_cd"

    def test_spaces_converted(self):
        assert normalize_gap_name("unit testing") == "testing"

    def test_ci_cd_variants(self):
        assert normalize_gap_name("ci") == "ci_cd"
        assert normalize_gap_name("cd") == "ci_cd"
        assert normalize_gap_name("continuous_integration") == "ci_cd"
        assert normalize_gap_name("github_actions") == "ci_cd"

    def test_container_variants(self):
        assert normalize_gap_name("docker") == "containerization"
        assert normalize_gap_name("containers") == "containerization"
        assert normalize_gap_name("k8s") == "kubernetes"
        assert normalize_gap_name("kubernetes") == "kubernetes"

    def test_auth_variants(self):
        assert normalize_gap_name("auth") == "authentication"
        assert normalize_gap_name("oauth") == "authentication"

    def test_performance_variants(self):
        assert normalize_gap_name("optimization") == "performance"
        assert normalize_gap_name("cache") == "caching"
        assert normalize_gap_name("redis") == "caching"

    def test_db_variants(self):
        assert normalize_gap_name("indexing") == "query_optimization"
        assert normalize_gap_name("database_indexing") == "query_optimization"
        assert normalize_gap_name("database_optimization") == "query_optimization"


class TestMergeDeduplicatesGaps:
    def test_synonyms_deduped_in_domain_merge(self):
        a = Skills(domains={
            "testing": DomainSkill(
                level=SkillLevel.BEGINNER,
                gaps=["unit_testing", "coverage"],
            ),
        })
        b = Skills(domains={
            "testing": DomainSkill(
                level=SkillLevel.PROFICIENT,
                gaps=["pytest", "test_coverage"],
            ),
        })
        merged = merge_profiles(a, b)
        gaps = merged.domains["testing"].gaps
        # "unit_testing" and "pytest" both map to "testing" → should be 1
        # "coverage" and "test_coverage" both map to "test_coverage" → should be 1
        assert "testing" in gaps
        assert "test_coverage" in gaps
        assert len(gaps) == 2

    def test_synonyms_deduped_in_integration_merge(self):
        a = Skills(integrations={
            "cloud": IntegrationSkill(
                level=SkillLevel.BEGINNER,
                gaps=["docker"],
            ),
        })
        b = Skills(integrations={
            "cloud": IntegrationSkill(
                level=SkillLevel.BEGINNER,
                gaps=["containers"],
            ),
        })
        merged = merge_profiles(a, b)
        gaps = merged.integrations["cloud"].gaps
        assert gaps == ["containerization"]

    def test_unique_gaps_preserved(self):
        a = Skills(domains={
            "backend": DomainSkill(gaps=["api_design", "testing"]),
        })
        b = Skills(domains={
            "backend": DomainSkill(gaps=["security"]),
        })
        merged = merge_profiles(a, b)
        gaps = merged.domains["backend"].gaps
        assert "api_design" in gaps
        assert "testing" in gaps
        assert "security" in gaps
        assert len(gaps) == 3
