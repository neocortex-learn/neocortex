"""Knowledge base health check engine."""

from __future__ import annotations

import re
from pathlib import Path

from neocortex.models import Language, LintIssue, LintReport, Profile
from neocortex.scanner.profile import normalize_gap_name


_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

_PENALTY = {"error": 10, "warning": 5, "info": 1}


def _collect_md_files(notes_dir: Path) -> list[Path]:
    return [
        f for f in notes_dir.rglob("*.md")
        if "concepts" not in f.parts
        and "insights" not in f.parts
        and f.name != "INDEX.md"
        and "diagrams" not in f.parts
        and ".flashcards" not in f.parts
    ]


def _collect_concept_files(notes_dir: Path) -> list[Path]:
    concepts_dir = notes_dir / "concepts"
    if not concepts_dir.exists():
        return []
    return list(concepts_dir.glob("*.md"))


def _parse_source_notes(content: str) -> list[str]:
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return []
    for line in fm_match.group(1).splitlines():
        if line.startswith("source_notes:"):
            raw = line.split(":", 1)[1].strip()
            if raw.startswith("[") and raw.endswith("]"):
                inner = raw[1:-1]
                if not inner.strip():
                    return []
                return [item.strip().strip("\"'") for item in inner.split(",") if item.strip()]
    return []


def _all_note_stems(notes_dir: Path) -> set[str]:
    stems: set[str] = set()
    for f in _collect_md_files(notes_dir):
        stems.add(f.stem)
    for f in _collect_concept_files(notes_dir):
        stems.add(f.stem)
    return stems


def _extract_wikilinks(content: str) -> list[str]:
    return _WIKILINK_RE.findall(content)


def check_orphan_notes(notes_dir: Path) -> list[LintIssue]:
    md_files = _collect_md_files(notes_dir)
    concept_files = _collect_concept_files(notes_dir)

    referenced_stems: set[str] = set()
    for cf in concept_files:
        try:
            content = cf.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for sn in _parse_source_notes(content):
            referenced_stems.add(Path(sn).stem)

    all_files = md_files + concept_files
    for f in all_files:
        try:
            content = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for link_target in _extract_wikilinks(content):
            referenced_stems.add(link_target.strip().lower().replace(" ", "-"))

    issues: list[LintIssue] = []
    for f in md_files:
        try:
            content = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        has_outgoing_links = bool(_WIKILINK_RE.search(content))
        is_referenced = f.stem.lower().replace(" ", "-") in {s.lower().replace(" ", "-") for s in referenced_stems}
        if not has_outgoing_links and not is_referenced:
            issues.append(LintIssue(
                type="orphan",
                severity="warning",
                message=f"{f.name} — no concept links",
                details=str(f),
                auto_fixable=True,
            ))
    return issues


def check_broken_links(notes_dir: Path) -> list[LintIssue]:
    known_stems = _all_note_stems(notes_dir)
    known_lower = {s.lower().replace(" ", "-") for s in known_stems}

    all_files = _collect_md_files(notes_dir) + _collect_concept_files(notes_dir)
    issues: list[LintIssue] = []

    for f in all_files:
        try:
            content = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for link_target in _extract_wikilinks(content):
            normalized_target = link_target.strip().lower().replace(" ", "-")
            if normalized_target not in known_lower:
                rel = f.relative_to(notes_dir) if f.is_relative_to(notes_dir) else f.name
                issues.append(LintIssue(
                    type="broken_link",
                    severity="warning",
                    message=f"{rel}: [[{link_target}]] → file not found",
                    details=str(f),
                    auto_fixable=True,
                ))
    return issues


def check_stale_concepts(notes_dir: Path) -> list[LintIssue]:
    concept_files = _collect_concept_files(notes_dir)
    note_filenames = {f.name for f in _collect_md_files(notes_dir)}
    issues: list[LintIssue] = []

    for cf in concept_files:
        try:
            content = cf.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        source_notes = _parse_source_notes(content)
        for sn in source_notes:
            if sn not in note_filenames:
                rel = cf.relative_to(notes_dir) if cf.is_relative_to(notes_dir) else cf.name
                issues.append(LintIssue(
                    type="stale",
                    severity="warning",
                    message=f"{rel}: source note {sn} not found",
                    details=str(cf),
                ))
    return issues


def check_coverage_gaps(notes_dir: Path, profile: Profile) -> list[LintIssue]:
    concept_stems = {normalize_gap_name(f.stem) for f in _collect_concept_files(notes_dir)}

    all_gaps: set[str] = set()
    for domain in profile.skills.domains.values():
        for g in domain.gaps:
            all_gaps.add(g)
    for integration in profile.skills.integrations.values():
        for g in integration.gaps:
            all_gaps.add(g)

    issues: list[LintIssue] = []
    for gap in sorted(all_gaps):
        normalized = normalize_gap_name(gap)
        if normalized not in concept_stems:
            issues.append(LintIssue(
                type="coverage_gap",
                severity="info",
                message=f"Gap \"{gap}\" has no notes in knowledge base",
            ))
    return issues


def check_duplicate_concepts(notes_dir: Path) -> list[LintIssue]:
    concept_files = _collect_concept_files(notes_dir)
    normalized_to_files: dict[str, list[str]] = {}

    for cf in concept_files:
        normalized = normalize_gap_name(cf.stem)
        normalized_to_files.setdefault(normalized, []).append(cf.name)

    issues: list[LintIssue] = []
    for normalized, files in normalized_to_files.items():
        if len(files) > 1:
            issues.append(LintIssue(
                type="duplicate",
                severity="warning",
                message=f"Duplicate concepts (same after normalization): {', '.join(files)}",
                auto_fixable=True,
            ))
    return issues


def check_decaying_concepts(notes_dir: Path) -> list[LintIssue]:
    """Find concepts whose confidence has decayed below threshold."""
    from neocortex.compiler import collect_all_concepts
    from neocortex.decay import DECAY_THRESHOLD, decayed_confidence

    concepts = collect_all_concepts(notes_dir / "concepts")
    issues: list[LintIssue] = []
    for c in concepts:
        if not c.last_updated:
            continue
        current = decayed_confidence(c.confidence, c.last_updated)
        if current < DECAY_THRESHOLD:
            issues.append(LintIssue(
                type="decaying",
                severity="warning",
                message=f"Concept \"{c.name}\" confidence decayed to {current:.2f} (last updated: {c.last_updated})",
            ))
    return issues


async def check_suggested_explorations(
    notes_dir: Path,
    profile: Profile,
    provider: object,
) -> list[LintIssue]:
    from neocortex.llm.base import LLMProvider

    if not isinstance(provider, LLMProvider):
        return []

    concept_files = _collect_concept_files(notes_dir)
    if not concept_files:
        return []

    concept_names: list[str] = []
    for cf in concept_files:
        concept_names.append(cf.stem.replace("-", " ").title())

    if len(concept_names) < 2:
        return []

    gap_list: list[str] = []
    for domain in profile.skills.domains.values():
        gap_list.extend(domain.gaps)
    for integration in profile.skills.integrations.values():
        gap_list.extend(integration.gaps)

    messages = [
        {
            "role": "system",
            "content": (
                "You analyze a developer's knowledge base to suggest interesting "
                "cross-domain explorations. Return a JSON array of objects with "
                "keys: concept_a, concept_b, suggestion. Each suggestion is one sentence "
                "explaining why exploring the intersection would be valuable. "
                "Return 1-3 suggestions maximum. Return ONLY JSON, no markdown fences."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Concepts in knowledge base: {', '.join(concept_names[:30])}\n"
                f"Current skill gaps: {', '.join(gap_list[:20]) if gap_list else 'None'}"
            ),
        },
    ]

    import json
    try:
        raw = await provider.chat(messages, json_mode=True)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return []

    if not isinstance(data, list):
        return []

    issues: list[LintIssue] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        a = item.get("concept_a", "")
        b = item.get("concept_b", "")
        suggestion = item.get("suggestion", "")
        if a and b and suggestion:
            issues.append(LintIssue(
                type="suggestion",
                severity="info",
                message=f"Consider exploring the intersection of {a} and {b}",
                details=suggestion,
            ))
    return issues


def fix_broken_links(notes_dir: Path) -> int:
    known_stems = _all_note_stems(notes_dir)
    known_lower = {s.lower().replace(" ", "-") for s in known_stems}

    all_files = _collect_md_files(notes_dir) + _collect_concept_files(notes_dir)
    fixed = 0

    for f in all_files:
        try:
            content = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        def _replace_broken(match: re.Match) -> str:
            nonlocal fixed
            link_target = match.group(1)
            display = match.group(0)
            normalized_target = link_target.strip().lower().replace(" ", "-")
            if normalized_target not in known_lower:
                fixed += 1
                pipe_match = re.search(r"\|(.+)", match.group(0)[2:-2])
                if pipe_match:
                    return pipe_match.group(1)
                return link_target
            return display

        new_content = _WIKILINK_RE.sub(_replace_broken, content)
        if new_content != content:
            import os
            import tempfile
            fd, tmp_path = tempfile.mkstemp(dir=str(f.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(new_content)
                os.replace(tmp_path, str(f))
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

    return fixed


def fix_orphan_notes(notes_dir: Path, provider: object | None = None) -> int:
    return 0


async def lint_knowledge_base(
    notes_dir: Path,
    profile: Profile,
    provider: object | None = None,
    language: Language = Language.EN,
) -> LintReport:
    report = LintReport()

    checks = {
        "orphan": check_orphan_notes(notes_dir),
        "broken_link": check_broken_links(notes_dir),
        "stale": check_stale_concepts(notes_dir),
        "coverage_gap": check_coverage_gaps(notes_dir, profile),
        "duplicate": check_duplicate_concepts(notes_dir),
        "decaying": check_decaying_concepts(notes_dir),
    }

    for check_type, issues in checks.items():
        report.stats[check_type] = len(issues)
        for issue in issues:
            report.issues.append(issue)
            report.score = max(0, report.score - _PENALTY.get(issue.severity, 0))

    if provider is not None:
        suggestions = await check_suggested_explorations(notes_dir, profile, provider)
        report.stats["suggestion"] = len(suggestions)
        for issue in suggestions:
            report.issues.append(issue)
            report.score = max(0, report.score - _PENALTY.get(issue.severity, 0))
    else:
        report.stats["suggestion"] = 0

    return report
