"""Skill growth tracking — save snapshots and compare over time."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from neocortex.models import Profile, ProfileSnapshot, Skills, SkillLevel


def save_snapshot(profile: Profile, data_dir: Path, notes_count: int = 0) -> None:
    snapshots_file = data_dir / "snapshots.json"
    snapshots = _load_snapshots(snapshots_file)

    total_lines = sum(lang.lines for lang in profile.skills.languages.values())
    projects: set[str] = set()
    for lang in profile.skills.languages.values():
        projects.update(lang.projects)

    snapshot = ProfileSnapshot(
        date=date.today().isoformat(),
        skills=profile.skills,
        total_lines=total_lines,
        total_projects=len(projects),
        notes_count=notes_count,
    )

    if snapshots and snapshots[-1].date == snapshot.date:
        snapshots[-1] = snapshot
    else:
        snapshots.append(snapshot)

    snapshots_file.write_text(
        json.dumps([s.model_dump(mode="json") for s in snapshots], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_snapshots(data_dir: Path) -> list[ProfileSnapshot]:
    return _load_snapshots(data_dir / "snapshots.json")


def _load_snapshots(path: Path) -> list[ProfileSnapshot]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [ProfileSnapshot(**item) for item in data]
    except (json.JSONDecodeError, TypeError, KeyError):
        return []


_LEVEL_ORDER = {
    SkillLevel.BEGINNER: 0,
    SkillLevel.PROFICIENT: 1,
    SkillLevel.ADVANCED: 2,
    SkillLevel.EXPERT: 3,
}


def compute_diff(old: ProfileSnapshot, new: ProfileSnapshot) -> dict:
    diff: dict = {
        "period": f"{old.date} → {new.date}",
        "lines_delta": new.total_lines - old.total_lines,
        "projects_delta": new.total_projects - old.total_projects,
        "notes_delta": new.notes_count - old.notes_count,
        "new_languages": [],
        "level_ups": [],
        "new_domains": [],
        "gaps_closed": [],
    }

    for lang, skill in new.skills.languages.items():
        if lang not in old.skills.languages:
            diff["new_languages"].append(lang)
        else:
            old_level = _LEVEL_ORDER.get(old.skills.languages[lang].level, 0)
            new_level = _LEVEL_ORDER.get(skill.level, 0)
            if new_level > old_level:
                diff["level_ups"].append({
                    "skill": lang,
                    "from": old.skills.languages[lang].level.value,
                    "to": skill.level.value,
                })

    for domain, skill in new.skills.domains.items():
        if domain not in old.skills.domains:
            diff["new_domains"].append(domain)
        else:
            old_level = _LEVEL_ORDER.get(old.skills.domains[domain].level, 0)
            new_level = _LEVEL_ORDER.get(skill.level, 0)
            if new_level > old_level:
                diff["level_ups"].append({
                    "skill": domain,
                    "from": old.skills.domains[domain].level.value,
                    "to": skill.level.value,
                })

    old_gaps: set[str] = set()
    for d in old.skills.domains.values():
        old_gaps.update(d.gaps)
    new_gaps: set[str] = set()
    for d in new.skills.domains.values():
        new_gaps.update(d.gaps)
    diff["gaps_closed"] = sorted(old_gaps - new_gaps)

    return diff
