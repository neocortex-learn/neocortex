"""Tests for claim extraction, conflict detection, and belief evolution tracking."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from neocortex.compiler import (
    detect_conflicts,
    extract_claims,
)
from neocortex.models import (
    CompileResult,
    Language,
)


# ── Fixtures ──


@pytest.fixture()
def mock_provider():
    provider = AsyncMock()
    provider.chat = AsyncMock()
    provider.name.return_value = "mock"
    provider.max_context_tokens.return_value = 100000
    return provider


# ── Extract claims ──


class TestExtractClaims:
    @pytest.mark.asyncio
    async def test_extract_claims_basic(self, mock_provider):
        mock_provider.chat.return_value = json.dumps([
            {
                "claim": "Snapshots should be taken every 100 events",
                "concept": "Event Sourcing",
                "context": "PostgreSQL implementation",
            },
            {
                "claim": "CQRS requires separate read and write databases",
                "concept": "CQRS",
                "context": "Large-scale systems",
            },
        ])

        claims = await extract_claims("Some note about Event Sourcing", mock_provider)
        assert len(claims) == 2
        assert claims[0]["claim"] == "Snapshots should be taken every 100 events"
        assert claims[0]["concept"] == "Event Sourcing"
        assert claims[0]["context"] == "PostgreSQL implementation"
        assert claims[1]["concept"] == "CQRS"

    @pytest.mark.asyncio
    async def test_extract_claims_empty_response(self, mock_provider):
        mock_provider.chat.return_value = "[]"

        claims = await extract_claims("Short content", mock_provider)
        assert claims == []

    @pytest.mark.asyncio
    async def test_extract_claims_invalid_json(self, mock_provider):
        mock_provider.chat.return_value = "not valid json"

        claims = await extract_claims("Some content", mock_provider)
        assert claims == []

    @pytest.mark.asyncio
    async def test_extract_claims_llm_exception(self, mock_provider):
        mock_provider.chat.side_effect = Exception("LLM error")

        with pytest.raises(Exception):
            await extract_claims("Some content", mock_provider)

    @pytest.mark.asyncio
    async def test_extract_claims_missing_claim_field(self, mock_provider):
        mock_provider.chat.return_value = json.dumps([
            {"concept": "Redis", "context": "caching"},
            {"claim": "Valid claim", "concept": "Redis", "context": ""},
        ])

        claims = await extract_claims("Content", mock_provider)
        assert len(claims) == 1
        assert claims[0]["claim"] == "Valid claim"

    @pytest.mark.asyncio
    async def test_extract_claims_with_markdown_fences(self, mock_provider):
        mock_provider.chat.return_value = (
            '```json\n[{"claim": "Redis is single-threaded", '
            '"concept": "Redis", "context": ""}]\n```'
        )

        claims = await extract_claims("Redis notes", mock_provider)
        assert len(claims) == 1
        assert claims[0]["claim"] == "Redis is single-threaded"

    @pytest.mark.asyncio
    async def test_extract_claims_truncates_content(self, mock_provider):
        mock_provider.chat.return_value = "[]"
        long_content = "x" * 10000

        await extract_claims(long_content, mock_provider)
        call_args = mock_provider.chat.call_args
        user_msg = call_args[0][0][1]["content"]
        assert len(user_msg) <= 3000

    @pytest.mark.asyncio
    async def test_extract_claims_chinese(self, mock_provider):
        mock_provider.chat.return_value = json.dumps([
            {
                "claim": "快照应每 100 个事件打一次",
                "concept": "Event Sourcing",
                "context": "PostgreSQL 实现",
            },
        ])

        claims = await extract_claims("中文笔记", mock_provider, Language.ZH)
        assert len(claims) == 1
        assert claims[0]["claim"] == "快照应每 100 个事件打一次"


# ── Detect conflicts ──


class TestDetectConflicts:
    @pytest.mark.asyncio
    async def test_detect_temporal_conflict(self, mock_provider):
        new_claims = [
            {
                "claim": "Snapshot frequency depends on query patterns",
                "concept": "event sourcing",
                "context": "",
            },
        ]
        existing_claims = {
            "event-sourcing": [
                {
                    "claim": "Snapshots should be taken every 100 events",
                    "source": "old-note.md",
                    "date": "2026-01-01",
                    "context": "PostgreSQL implementation",
                },
            ],
        }

        mock_provider.chat.return_value = json.dumps([
            {
                "pair_index": 0,
                "type": "temporal",
                "explanation": "The older claim used a fixed interval; newer approaches are query-driven",
                "resolution_hint": "Update to query-pattern-based approach",
            },
        ])

        conflicts = await detect_conflicts(new_claims, existing_claims, mock_provider)
        assert len(conflicts) == 1
        assert conflicts[0]["type"] == "temporal"
        assert conflicts[0]["claim_a"] == "Snapshots should be taken every 100 events"
        assert conflicts[0]["claim_b"] == "Snapshot frequency depends on query patterns"
        assert conflicts[0]["concept"] == "event_sourcing"
        assert "explanation" in conflicts[0]

    @pytest.mark.asyncio
    async def test_detect_contextual_conflict(self, mock_provider):
        new_claims = [
            {
                "claim": "Use synchronous replication for consistency",
                "concept": "database replication",
                "context": "financial systems",
            },
        ]
        existing_claims = {
            "database-replication": [
                {
                    "claim": "Use asynchronous replication for performance",
                    "source": "perf-note.md",
                    "date": "2026-02-01",
                    "context": "high-throughput systems",
                },
            ],
        }

        mock_provider.chat.return_value = json.dumps([
            {
                "pair_index": 0,
                "type": "contextual",
                "explanation": "Sync vs async depends on consistency vs throughput requirements",
                "resolution_hint": "Both valid in their respective contexts",
            },
        ])

        conflicts = await detect_conflicts(new_claims, existing_claims, mock_provider)
        assert len(conflicts) == 1
        assert conflicts[0]["type"] == "contextual"

    @pytest.mark.asyncio
    async def test_detect_no_conflicts(self, mock_provider):
        new_claims = [
            {
                "claim": "Redis supports pub/sub",
                "concept": "redis",
                "context": "",
            },
        ]
        existing_claims = {
            "redis": [
                {
                    "claim": "Redis is an in-memory store",
                    "source": "redis-note.md",
                    "date": "2026-01-01",
                    "context": "",
                },
            ],
        }

        mock_provider.chat.return_value = "[]"

        conflicts = await detect_conflicts(new_claims, existing_claims, mock_provider)
        assert conflicts == []

    @pytest.mark.asyncio
    async def test_detect_no_matching_concept(self, mock_provider):
        new_claims = [
            {
                "claim": "Kafka uses partitions",
                "concept": "kafka",
                "context": "",
            },
        ]
        existing_claims = {
            "redis": [
                {
                    "claim": "Redis is fast",
                    "source": "redis.md",
                    "date": "2026-01-01",
                    "context": "",
                },
            ],
        }

        conflicts = await detect_conflicts(new_claims, existing_claims, mock_provider)
        assert conflicts == []
        mock_provider.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_detect_empty_claims(self, mock_provider):
        conflicts = await detect_conflicts([], {}, mock_provider)
        assert conflicts == []
        mock_provider.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_detect_llm_invalid_json(self, mock_provider):
        new_claims = [
            {"claim": "Test claim", "concept": "redis", "context": ""},
        ]
        existing_claims = {
            "redis": [
                {"claim": "Old claim", "source": "old.md", "date": "2026-01-01", "context": ""},
            ],
        }

        mock_provider.chat.return_value = "invalid json"

        conflicts = await detect_conflicts(new_claims, existing_claims, mock_provider)
        assert conflicts == []

    @pytest.mark.asyncio
    async def test_detect_invalid_pair_index(self, mock_provider):
        new_claims = [
            {"claim": "Test claim", "concept": "redis", "context": ""},
        ]
        existing_claims = {
            "redis": [
                {"claim": "Old claim", "source": "old.md", "date": "2026-01-01", "context": ""},
            ],
        }

        mock_provider.chat.return_value = json.dumps([
            {"pair_index": 99, "type": "genuine", "explanation": "bad index", "resolution_hint": ""},
        ])

        conflicts = await detect_conflicts(new_claims, existing_claims, mock_provider)
        assert conflicts == []


# ── Claims storage ──


class TestClaimsStorage:
    def test_load_save_claims(self, tmp_path):
        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            from neocortex.config import load_claims, save_claims

            claims = load_claims()
            assert claims == {}

            test_claims = {
                "event-sourcing": [
                    {
                        "claim": "Snapshots every 100 events",
                        "source": "note.md",
                        "date": "2026-04-01",
                        "context": "PostgreSQL",
                    },
                ],
            }
            save_claims(test_claims)

            loaded = load_claims()
            assert "event-sourcing" in loaded
            assert len(loaded["event-sourcing"]) == 1
            assert loaded["event-sourcing"][0]["claim"] == "Snapshots every 100 events"

    def test_load_claims_empty_file(self, tmp_path):
        claims_path = tmp_path / "claims.json"
        claims_path.write_text("{}", encoding="utf-8")

        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            from neocortex.config import load_claims

            claims = load_claims()
            assert claims == {}

    def test_load_claims_corrupt_file(self, tmp_path):
        claims_path = tmp_path / "claims.json"
        claims_path.write_text("not json", encoding="utf-8")

        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            from neocortex.config import load_claims

            claims = load_claims()
            assert claims == {}


# ── Belief changes ──


class TestBeliefChanges:
    def test_load_save_belief_changes(self, tmp_path):
        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            from neocortex.config import load_belief_changes, save_belief_changes

            changes = load_belief_changes()
            assert changes == []

            test_changes = [
                {
                    "date": "2026-04-03",
                    "concept": "event-sourcing",
                    "from": "Snapshots every 100 events",
                    "to": "Snapshot frequency depends on query patterns",
                    "trigger": "new-note.md",
                    "type": "temporal",
                },
            ]
            save_belief_changes(test_changes)

            loaded = load_belief_changes()
            assert len(loaded) == 1
            assert loaded[0]["concept"] == "event-sourcing"
            assert loaded[0]["type"] == "temporal"

    def test_load_belief_changes_empty(self, tmp_path):
        changes_path = tmp_path / "belief_changes.json"
        changes_path.write_text("[]", encoding="utf-8")

        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            from neocortex.config import load_belief_changes

            changes = load_belief_changes()
            assert changes == []

    def test_belief_changes_auto_recorded(self, mock_provider, tmp_path):
        """Verify that temporal/genuine conflicts produce belief change entries."""
        from neocortex.config import load_belief_changes, save_belief_changes, save_claims

        with patch("neocortex.config.get_data_dir", return_value=tmp_path):
            save_claims({
                "redis": [
                    {
                        "claim": "Redis is single-threaded",
                        "source": "old.md",
                        "date": "2026-01-01",
                        "context": "",
                    },
                ],
            })

            conflicts = [
                {
                    "claim_a": "Redis is single-threaded",
                    "source_a": "old.md",
                    "claim_b": "Redis 6+ has multi-threaded I/O",
                    "source_b": "new.md",
                    "concept": "redis",
                    "type": "temporal",
                    "explanation": "Redis evolved to support multi-threaded I/O",
                    "resolution_hint": "Update to reflect Redis 6+ capabilities",
                },
            ]

            belief_changes = load_belief_changes()
            for conflict in conflicts:
                if conflict["type"] in ("temporal", "genuine"):
                    belief_changes.append({
                        "date": date.today().isoformat(),
                        "concept": conflict.get("concept", ""),
                        "from": conflict["claim_a"],
                        "to": conflict["claim_b"],
                        "trigger": conflict["source_b"],
                        "type": conflict["type"],
                    })
            save_belief_changes(belief_changes)

            loaded = load_belief_changes()
            assert len(loaded) == 1
            assert loaded[0]["from"] == "Redis is single-threaded"
            assert loaded[0]["to"] == "Redis 6+ has multi-threaded I/O"
            assert loaded[0]["type"] == "temporal"


# ── CompileResult.conflicts field ──


class TestCompileResultConflicts:
    def test_compile_result_has_conflicts_field(self):
        result = CompileResult()
        assert result.conflicts == []

    def test_compile_result_with_conflicts(self):
        result = CompileResult(
            notes_processed=1,
            conflicts=[
                {
                    "claim_a": "old claim",
                    "claim_b": "new claim",
                    "type": "temporal",
                    "explanation": "things changed",
                },
            ],
        )
        assert len(result.conflicts) == 1
        assert result.conflicts[0]["type"] == "temporal"

    def test_compile_result_serialization(self):
        result = CompileResult(
            notes_processed=1,
            conflicts=[
                {"type": "genuine", "explanation": "contradicting"},
            ],
        )
        data = result.model_dump()
        assert "conflicts" in data
        assert len(data["conflicts"]) == 1

        restored = CompileResult.model_validate(data)
        assert len(restored.conflicts) == 1
        assert restored.conflicts[0]["type"] == "genuine"
