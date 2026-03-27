"""GitHub opportunity matcher — find good-first-issues and trending repos."""

from __future__ import annotations

import json
import subprocess
from datetime import date

from neocortex.matcher.base import build_skill_vector, score_opportunity
from neocortex.models import Opportunity, Profile


async def find_oss_opportunities(profile: Profile, max_results: int = 10) -> list[Opportunity]:
    """Find open source opportunities matching the profile's languages."""
    skill_vector = build_skill_vector(profile)

    # Get user's top languages
    top_langs = sorted(
        profile.skills.languages.items(),
        key=lambda x: x[1].lines,
        reverse=True,
    )[:3]

    opportunities: list[Opportunity] = []

    for lang_name, lang_skill in top_langs:
        issues = _search_good_first_issues(lang_name)
        for issue in issues[:max_results // len(top_langs) or 3]:
            # Extract required skills from labels and repo topics
            required = [lang_name] + issue.get("topics", [])
            score, matched, missing = score_opportunity(skill_vector, required)
            opportunities.append(Opportunity(
                type="oss",
                title=issue["title"],
                url=issue["url"],
                source="github",
                skills_matched=matched,
                skills_missing=missing,
                match_score=score,
                difficulty=issue.get("difficulty", "beginner"),
                fetched_at=date.today().isoformat(),
            ))

    opportunities.sort(key=lambda x: x.match_score, reverse=True)
    return opportunities[:max_results]


_topic_cache: dict[str, list[str]] = {}


def _search_good_first_issues(language: str) -> list[dict]:
    """Search GitHub for good-first-issues in a language using gh CLI."""
    try:
        result = subprocess.run(
            [
                "gh", "search", "issues",
                "--label=good first issue",
                f"--language={language}",
                "--state=open",
                "--sort=updated",
                "--limit=10",
                "--json=title,url,repository,labels,updatedAt",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        items = json.loads(result.stdout)
        issues = []
        for item in items:
            repo = item.get("repository", {})
            labels = [l.get("name", "") for l in item.get("labels", [])]
            difficulty = "beginner"
            if any("medium" in la.lower() or "intermediate" in la.lower() for la in labels):
                difficulty = "intermediate"
            if any("hard" in la.lower() or "advanced" in la.lower() for la in labels):
                difficulty = "advanced"
            # Get repo topics (cached to avoid N subprocess calls)
            topics = []
            repo_name = repo.get("nameWithOwner", "")
            if repo_name:
                if repo_name not in _topic_cache:
                    _topic_cache[repo_name] = _get_repo_topics(repo_name)
                topics = _topic_cache[repo_name]
            issues.append({
                "title": f"[{repo.get('name', '?')}] {item.get('title', '')}",
                "url": item.get("url", ""),
                "topics": topics,
                "difficulty": difficulty,
            })
        return issues
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        return []


def _get_repo_topics(repo_name: str) -> list[str]:
    """Get repository topics."""
    try:
        result = subprocess.run(
            ["gh", "repo", "view", repo_name, "--json=repositoryTopics", "-q", ".repositoryTopics[].name"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return [t.strip() for t in result.stdout.strip().split("\n") if t.strip()][:5]
    except (subprocess.TimeoutExpired, OSError):
        pass
    return []
