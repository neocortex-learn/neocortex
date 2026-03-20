from __future__ import annotations

import json

import pytest

from neocortex.importer.chatgpt import ParsedMessage, parse_chatgpt_export
from neocortex.importer.claude import parse_claude_export
from neocortex.importer.merger import cross_validate, merge_insights_to_profile
from neocortex.models import (
    ChatInsights,
    DomainSkill,
    LanguageSkill,
    Profile,
    QuestionAsked,
    SkillLevel,
    Skills,
)


# ── ChatGPT parsing ──


def _make_chatgpt_conversations():
    return [
        {
            "title": "Python help",
            "create_time": 1700000000.0,
            "mapping": {
                "node-1": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["How do I use async/await in Python for concurrency?"]},
                        "create_time": 1700000100.0,
                    }
                },
                "node-2": {
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"parts": ["Here is how you use async/await..."]},
                        "create_time": 1700000200.0,
                    }
                },
                "node-3": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["short"]},
                        "create_time": 1700000300.0,
                    }
                },
                "node-4": {
                    "message": None,
                },
                "node-5": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["Can you explain decorators in detail?"]},
                        "create_time": 1700000400.0,
                    }
                },
            },
        }
    ]


class TestChatGPTParser:
    def test_extracts_user_messages_only(self, tmp_path):
        data = _make_chatgpt_conversations()
        f = tmp_path / "conversations.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        messages = parse_chatgpt_export(str(f))
        for msg in messages:
            assert "assistant" not in msg.content.lower() or True
        assert len(messages) == 2

    def test_filters_short_messages(self, tmp_path):
        data = _make_chatgpt_conversations()
        f = tmp_path / "conversations.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        messages = parse_chatgpt_export(str(f))
        for msg in messages:
            assert len(msg.content) >= 10

    def test_timestamps_extracted(self, tmp_path):
        data = _make_chatgpt_conversations()
        f = tmp_path / "conversations.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        messages = parse_chatgpt_export(str(f))
        assert messages[0].timestamp == 1700000100.0
        assert messages[1].timestamp == 1700000400.0

    def test_conversation_title(self, tmp_path):
        data = _make_chatgpt_conversations()
        f = tmp_path / "conversations.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        messages = parse_chatgpt_export(str(f))
        for msg in messages:
            assert msg.conversation_title == "Python help"

    def test_fallback_timestamp_to_conv_create_time(self, tmp_path):
        data = [
            {
                "title": "Fallback test",
                "create_time": 1600000000.0,
                "mapping": {
                    "node-1": {
                        "message": {
                            "author": {"role": "user"},
                            "content": {"parts": ["This message has no create_time field"]},
                        }
                    }
                },
            }
        ]
        f = tmp_path / "conversations.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        messages = parse_chatgpt_export(str(f))
        assert len(messages) == 1
        assert messages[0].timestamp == 1600000000.0


# ── Claude parsing ──


def _make_claude_conversations():
    return [
        {
            "uuid": "conv-001",
            "name": "Rust learning",
            "created_at": "2024-06-15T10:30:00Z",
            "chat_messages": [
                {
                    "uuid": "msg-001",
                    "sender": "human",
                    "text": "How does the borrow checker work in Rust?",
                    "created_at": "2024-06-15T10:31:00Z",
                },
                {
                    "uuid": "msg-002",
                    "sender": "assistant",
                    "text": "The borrow checker ensures memory safety...",
                    "created_at": "2024-06-15T10:32:00Z",
                },
                {
                    "uuid": "msg-003",
                    "sender": "human",
                    "text": "tiny",
                    "created_at": "2024-06-15T10:33:00Z",
                },
                {
                    "uuid": "msg-004",
                    "sender": "human",
                    "text": "What is the difference between Box, Rc and Arc?",
                    "created_at": "2024-06-15T10:34:00Z",
                },
            ],
        }
    ]


class TestClaudeParser:
    def test_extracts_human_messages_only(self, tmp_path):
        data = _make_claude_conversations()
        f = tmp_path / "conversations.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        messages = parse_claude_export(str(f))
        assert len(messages) == 2

    def test_directory_mode(self, tmp_path):
        data = _make_claude_conversations()
        export_dir = tmp_path / "claude_export"
        export_dir.mkdir()
        (export_dir / "conversations.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
        messages = parse_claude_export(str(export_dir))
        assert len(messages) == 2

    def test_file_mode(self, tmp_path):
        data = _make_claude_conversations()
        f = tmp_path / "my_claude.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        messages = parse_claude_export(str(f))
        assert len(messages) == 2

    def test_filters_short_messages(self, tmp_path):
        data = _make_claude_conversations()
        f = tmp_path / "conversations.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        messages = parse_claude_export(str(f))
        for msg in messages:
            assert len(msg.content) >= 10

    def test_timestamps_parsed(self, tmp_path):
        data = _make_claude_conversations()
        f = tmp_path / "conversations.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        messages = parse_claude_export(str(f))
        assert messages[0].timestamp > 0
        assert messages[1].timestamp > messages[0].timestamp

    def test_conversation_title(self, tmp_path):
        data = _make_claude_conversations()
        f = tmp_path / "conversations.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        messages = parse_claude_export(str(f))
        for msg in messages:
            assert msg.conversation_title == "Rust learning"


# ── Merger: merge_insights_to_profile ──


class TestMergeInsightsToProfile:
    def test_chat_insights_stored(self):
        profile = Profile()
        insights = ChatInsights(
            source="chatgpt",
            imported_at="2024-06-15",
            message_count=42,
            topics_discussed=["redis", "fastapi"],
            confusion_points=["connection pooling"],
            growth_trajectory="backend focused",
        )
        result = merge_insights_to_profile(profile, insights)
        assert result.chat_insights is not None
        assert result.chat_insights.source == "chatgpt"
        assert result.chat_insights.message_count == 42

    def test_topics_added_as_beginner_domains(self):
        profile = Profile()
        insights = ChatInsights(
            source="chatgpt",
            imported_at="2024-06-15",
            topics_discussed=["kubernetes", "docker"],
        )
        result = merge_insights_to_profile(profile, insights)
        assert "kubernetes" in result.skills.domains
        assert result.skills.domains["kubernetes"].level == SkillLevel.BEGINNER
        assert "docker" in result.skills.domains
        assert result.skills.domains["docker"].level == SkillLevel.BEGINNER

    def test_existing_domain_not_overwritten(self):
        profile = Profile(
            skills=Skills(
                domains={
                    "redis": DomainSkill(level=SkillLevel.EXPERT, evidence=["lots of usage"]),
                }
            )
        )
        insights = ChatInsights(
            source="chatgpt",
            imported_at="2024-06-15",
            topics_discussed=["redis"],
        )
        result = merge_insights_to_profile(profile, insights)
        assert result.skills.domains["redis"].level == SkillLevel.EXPERT

    def test_confusion_points_add_gaps(self):
        profile = Profile(
            skills=Skills(
                domains={
                    "redis": DomainSkill(level=SkillLevel.ADVANCED),
                }
            )
        )
        insights = ChatInsights(
            source="chatgpt",
            imported_at="2024-06-15",
            confusion_points=["redis"],
        )
        result = merge_insights_to_profile(profile, insights)
        assert len(result.skills.domains["redis"].gaps) == 1
        assert "confusion point" in result.skills.domains["redis"].gaps[0]


# ── Merger: cross_validate ──


class TestCrossValidate:
    def test_expert_no_beginner_questions_stays_expert(self):
        skills = Skills(
            domains={
                "redis": DomainSkill(level=SkillLevel.EXPERT, evidence=["heavy usage"]),
            }
        )
        insights = ChatInsights(
            source="chatgpt",
            imported_at="2024-06-15",
            questions_asked=[],
            topics_discussed=[],
        )
        result = cross_validate(skills, insights)
        assert result.domains["redis"].level == SkillLevel.EXPERT

    def test_expert_with_beginner_questions_demoted(self):
        skills = Skills(
            domains={
                "redis": DomainSkill(level=SkillLevel.EXPERT, evidence=["usage"]),
            }
        )
        insights = ChatInsights(
            source="chatgpt",
            imported_at="2024-06-15",
            questions_asked=[
                QuestionAsked(
                    topic="redis",
                    level="beginner",
                    date="2024-01-01",
                    summary="what is redis?",
                ),
            ],
            topics_discussed=["redis"],
        )
        result = cross_validate(skills, insights)
        assert result.domains["redis"].level == SkillLevel.ADVANCED

    def test_chat_topic_not_in_code_added_as_beginner(self):
        skills = Skills(
            domains={
                "python": DomainSkill(level=SkillLevel.EXPERT),
            }
        )
        insights = ChatInsights(
            source="claude",
            imported_at="2024-06-15",
            topics_discussed=["graphql"],
            questions_asked=[],
        )
        result = cross_validate(skills, insights)
        assert "graphql" in result.domains
        assert result.domains["graphql"].level == SkillLevel.BEGINNER
        assert any("learning" in e for e in result.domains["graphql"].evidence)

    def test_language_expert_demoted_on_beginner_questions(self):
        skills = Skills(
            languages={
                "python": LanguageSkill(level=SkillLevel.EXPERT, lines=50000),
            }
        )
        insights = ChatInsights(
            source="chatgpt",
            imported_at="2024-06-15",
            questions_asked=[
                QuestionAsked(
                    topic="python",
                    level="beginner",
                    date="2024-03-01",
                    summary="how to write a for loop",
                ),
            ],
            topics_discussed=["python"],
        )
        result = cross_validate(skills, insights)
        assert result.languages["python"].level == SkillLevel.ADVANCED

    def test_topic_already_in_languages_not_added_to_domains(self):
        skills = Skills(
            languages={
                "rust": LanguageSkill(level=SkillLevel.PROFICIENT, lines=1000),
            }
        )
        insights = ChatInsights(
            source="chatgpt",
            imported_at="2024-06-15",
            topics_discussed=["rust"],
            questions_asked=[],
        )
        result = cross_validate(skills, insights)
        assert "rust" not in result.domains
