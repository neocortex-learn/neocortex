"""Merge chat insights into user profile and cross-validate with code skills."""

from __future__ import annotations

from neocortex.models import (
    ChatInsights,
    DomainSkill,
    Profile,
    SkillLevel,
    Skills,
)

_BEGINNER_LEVELS = {"beginner"}
_LEVEL_ORDER: list[SkillLevel] = [
    SkillLevel.BEGINNER,
    SkillLevel.PROFICIENT,
    SkillLevel.ADVANCED,
    SkillLevel.EXPERT,
]


def _skill_level_index(level: SkillLevel) -> int:
    return _LEVEL_ORDER.index(level)


def _demote(level: SkillLevel) -> SkillLevel:
    idx = _skill_level_index(level)
    if idx > 0:
        return _LEVEL_ORDER[idx - 1]
    return level


def merge_insights_to_profile(profile: Profile, insights: ChatInsights) -> Profile:
    """Merge chat insights into user profile.

    - Stores the insights in profile.chat_insights.
    - Adds confusion points as gaps in domain skills.
    - Adds discussed topics as domains if not already present.
    """
    profile.chat_insights = insights

    for topic in insights.topics_discussed:
        normalized = topic.lower().replace(" ", "_")
        if normalized not in profile.skills.domains:
            profile.skills.domains[normalized] = DomainSkill(
                level=SkillLevel.BEGINNER,
                evidence=[f"discussed in {insights.source} chat history"],
            )

    for point in insights.confusion_points:
        normalized = point.lower().replace(" ", "_")
        if normalized in profile.skills.domains:
            domain = profile.skills.domains[normalized]
            gap_text = f"confusion point from {insights.source} import"
            if gap_text not in domain.gaps:
                domain.gaps.append(gap_text)
        else:
            profile.skills.domains[normalized] = DomainSkill(
                level=SkillLevel.BEGINNER,
                gaps=[f"confusion point from {insights.source} import"],
            )

    return profile


def cross_validate(skills: Skills, insights: ChatInsights) -> Skills:
    """Cross-validate code-scanned skills against chat insights.

    Rules:
    1. Code says Expert, chat never asked about it  -> confirm Expert
    2. Code says Expert, but chat has beginner-level questions -> demote to Advanced
    3. Not in code, but frequently discussed in chat -> mark as "learning" (Beginner)
    4. Neither in code nor chat -> remains absent (blind spot)
    """
    chat_topics: set[str] = set()
    for t in insights.topics_discussed:
        chat_topics.add(t.lower().replace(" ", "_"))

    beginner_question_topics: set[str] = set()
    for q in insights.questions_asked:
        if q.level in _BEGINNER_LEVELS:
            beginner_question_topics.add(q.topic.lower().replace(" ", "_"))

    for name, domain in skills.domains.items():
        normalized = name.lower().replace(" ", "_")

        if domain.level == SkillLevel.EXPERT and normalized in beginner_question_topics:
            domain.level = _demote(domain.level)
            domain.evidence.append(
                f"demoted: beginner questions found in {insights.source} chat"
            )

    for lang_name, lang_skill in skills.languages.items():
        normalized = lang_name.lower().replace(" ", "_")
        if lang_skill.level == SkillLevel.EXPERT and normalized in beginner_question_topics:
            lang_skill.level = _demote(lang_skill.level)

    for topic in chat_topics:
        if topic not in skills.domains:
            all_lang_keys = {k.lower().replace(" ", "_") for k in skills.languages}
            all_domain_keys = {k.lower().replace(" ", "_") for k in skills.domains}
            all_integration_keys = {k.lower().replace(" ", "_") for k in skills.integrations}
            all_arch_keys = {k.lower().replace(" ", "_") for k in skills.architecture}
            all_keys = all_lang_keys | all_domain_keys | all_integration_keys | all_arch_keys

            if topic not in all_keys:
                skills.domains[topic] = DomainSkill(
                    level=SkillLevel.BEGINNER,
                    evidence=[f"learning: frequently discussed in {insights.source} chat"],
                )

    return skills
