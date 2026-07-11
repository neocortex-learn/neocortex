"""Concept compilation engine — extract concepts, generate entries, insert wikilinks."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
import tempfile
from collections.abc import Callable
from datetime import date
from pathlib import Path


from neocortex.llm.base import LLMProvider
from neocortex.models import (
    CompileResult,
    ConceptEntry,
    ConceptRef,
    Language,
    Profile,
    SkillLevel,
)
from neocortex.scanner.profile import normalize_gap_name


# ── Concept extraction ──


async def extract_concepts(
    content: str,
    provider: LLMProvider,
    language: Language = Language.EN,
) -> list[ConceptRef]:
    """Extract core concepts from note content via a single LLM call."""
    truncated = content[:3000]
    lang_instruction = "Respond in Chinese." if language == Language.ZH else "Respond in English."

    messages = [
        {
            "role": "system",
            "content": (
                "You extract core technical concepts from developer learning notes. "
                "Return a JSON array of objects with keys: name, definition_brief, related_to. "
                "Extract 3-8 concepts per note. "
                "Concept granularity should be at the level of a specific technique or pattern "
                "(e.g. 'Event Sourcing', 'Connection Pooling'), not too broad ('Python') "
                "or too narrow ('Python list comprehension syntax'). "
                "definition_brief is one sentence. "
                "related_to is a list of related concept names. "
                f"{lang_instruction} "
                "Output ONLY a JSON array, no markdown fences."
            ),
        },
        {
            "role": "user",
            "content": truncated,
        },
    ]

    raw = await provider.chat(messages, json_mode=True)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    refs: list[ConceptRef] = []
    for item in data:
        if not isinstance(item, dict) or "name" not in item:
            continue
        refs.append(ConceptRef(
            name=item["name"],
            definition_brief=item.get("definition_brief", ""),
            related_to=item.get("related_to", []),
        ))
    return refs


# ── Claim extraction ──


async def extract_claims(
    content: str,
    provider: LLMProvider,
    language: Language = Language.EN,
) -> list[dict]:
    """Extract core factual claims from note content.

    Returns [{claim, concept, context}].
    """
    truncated = content[:3000]
    lang_instruction = "用中文输出。" if language == Language.ZH else "Respond in English."

    messages = [
        {
            "role": "system",
            "content": (
                "从以下笔记中提取 3-5 个核心声明（factual claims）。"
                "每个声明是一个可以被验证或反驳的具体论断。"
                "不要提取观点或偏好，只提取事实性声明。"
                f"输出 JSON 数组: "
                '[{"claim": "...", "concept": "相关概念名", "context": "适用条件"}] '
                f"{lang_instruction} "
                "Output ONLY a JSON array, no markdown fences."
            ),
        },
        {
            "role": "user",
            "content": truncated,
        },
    ]

    raw = await provider.chat(messages, json_mode=True)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    claims: list[dict] = []
    for item in data:
        if not isinstance(item, dict) or "claim" not in item:
            continue
        claims.append({
            "claim": item["claim"],
            "concept": item.get("concept", ""),
            "context": item.get("context", ""),
        })
    return claims


# ── Conflict detection ──


async def detect_conflicts(
    new_claims: list[dict],
    existing_claims: dict[str, list[dict]],
    provider: LLMProvider,
    language: Language = Language.EN,
) -> list[dict]:
    """Compare new claims against existing ones. Returns conflicts.

    Each conflict: {claim_a, source_a, claim_b, source_b, concept, type, explanation, resolution_hint}
    type: "temporal" | "contextual" | "genuine"
    """
    normalized_existing: dict[str, list[dict]] = {}
    for key, value in existing_claims.items():
        normalized_existing[normalize_gap_name(key)] = value

    pairs: list[dict] = []
    for nc in new_claims:
        concept_name = normalize_gap_name(nc.get("concept", ""))
        if not concept_name or concept_name not in normalized_existing:
            continue
        for ec in normalized_existing[concept_name]:
            pairs.append({
                "index": len(pairs),
                "claim_a": ec["claim"],
                "source_a": ec.get("source", ""),
                "claim_b": nc["claim"],
                "concept": concept_name,
            })

    if not pairs:
        return []

    pairs_text = ""
    for p in pairs:
        pairs_text += (
            f"Pair {p['index']}:\n"
            f"  A (existing): {p['claim_a']}\n"
            f"  B (new): {p['claim_b']}\n\n"
        )

    lang_instruction = "用中文输出。" if language == Language.ZH else "Respond in English."

    messages = [
        {
            "role": "system",
            "content": (
                "比较以下声明对，判断是否存在冲突：\n\n"
                f"{pairs_text}"
                "对每一对，分类为：\n"
                "- temporal: 时间差异导致（技术演进）\n"
                "- contextual: 不同上下文下各自成立\n"
                "- genuine: 真正的矛盾\n"
                "- no_conflict: 实际不矛盾\n\n"
                '输出 JSON 数组: [{"pair_index": 0, "type": "...", "explanation": "...", "resolution_hint": "..."}]\n'
                "只返回 type 不是 no_conflict 的。如果没有冲突，返回空数组 []。\n"
                f"{lang_instruction} "
                "Output ONLY a JSON array, no markdown fences."
            ),
        },
        {
            "role": "user",
            "content": "请分析上述声明对。",
        },
    ]

    raw = await provider.chat(messages, json_mode=True)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    conflicts: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        conflict_type = item.get("type", "no_conflict")
        if conflict_type == "no_conflict":
            continue
        pair_index = item.get("pair_index", -1)
        if not isinstance(pair_index, int) or pair_index < 0 or pair_index >= len(pairs):
            continue
        pair = pairs[pair_index]
        conflicts.append({
            "claim_a": pair["claim_a"],
            "source_a": pair["source_a"],
            "claim_b": pair["claim_b"],
            "source_b": "",
            "concept": pair["concept"],
            "type": conflict_type,
            "explanation": item.get("explanation", ""),
            "resolution_hint": item.get("resolution_hint", ""),
        })

    return conflicts


# ── Concept entry generation ──


async def generate_concept_entry(
    name: str,
    source_notes: list[dict],
    related_concepts: list[str],
    profile: Profile,
    provider: LLMProvider,
    language: Language = Language.EN,
) -> str:
    """Generate a full Markdown concept entry (with frontmatter) via LLM."""
    today = date.today().isoformat()
    note_filenames = [n["filename"] for n in source_notes]

    if language == Language.ZH:
        section_oneliner = "一句话理解"
        section_core = "核心要点"
        section_sources = "来源笔记"
        section_related = "关联概念"
        section_open = "开放问题"
        lang_instruction = "用中文写作。"
    else:
        section_oneliner = "One-liner"
        section_core = "Core Points"
        section_sources = "Source Notes"
        section_related = "Related Concepts"
        section_open = "Open Questions"
        lang_instruction = "Write in English."

    notes_context = ""
    for n in source_notes:
        notes_context += f"\n### {n.get('title', n['filename'])}\n{n.get('content_preview', '')}\n"

    messages = [
        {
            "role": "system",
            "content": (
                "You are generating a concept entry for a personal knowledge wiki. "
                f"{lang_instruction} "
                "Generate ONLY the body sections (no frontmatter, no top-level heading). "
                f"Sections: ## {section_oneliner}, ## {section_core}, ## {section_open}. "
                "Be concise and precise. "
                "For Core Points, synthesize from all source notes. "
                "For Open Questions, identify 1-3 unanswered questions based on the content."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Concept: {name}\n"
                f"Related: {', '.join(related_concepts) if related_concepts else 'None'}\n"
                f"\nSource notes:\n{notes_context}"
            ),
        },
    ]

    body = await provider.chat(messages)

    source_lines = f"\n## {section_sources}\n"
    for n in source_notes:
        stem = Path(n["filename"]).stem
        desc = n.get("title", stem)
        source_lines += f"- [[{stem}]] \u2014 {desc}\n"

    related_lines = ""
    if related_concepts:
        related_lines = f"\n## {section_related}\n"
        for rc in related_concepts:
            related_lines += f"- [[{rc}]]\n"

    aliases = _generate_aliases(name)
    # f-string 表达式内不能出现反斜杠/同类引号（PEP 701 之前的 3.10/3.11），先在外面拼好
    aliases_yaml = ", ".join('"' + a + '"' for a in aliases)
    related_yaml = ", ".join('"' + rc + '"' for rc in related_concepts)
    sources_yaml = ", ".join('"' + fn + '"' for fn in note_filenames)
    frontmatter = (
        f"---\n"
        f"type: concept\n"
        f"name: {name}\n"
        f"aliases: [{aliases_yaml}]\n"
        f"related_concepts: [{related_yaml}]\n"
        f"skill_level: {SkillLevel.BEGINNER.value}\n"
        f"confidence: 0.3\n"
        f"evidence_count: {len(source_notes)}\n"
        f"last_updated: {today}\n"
        f"source_notes: [{sources_yaml}]\n"
        f"---\n"
    )

    return f"{frontmatter}\n# {name}\n\n{body}\n{source_lines}{related_lines}"


def _generate_aliases(name: str) -> list[str]:
    """Generate common aliases for a concept name."""
    aliases: list[str] = []
    slug = name.strip().lower().replace(" ", "-")
    if slug != name:
        aliases.append(slug)
    snake = name.strip().lower().replace(" ", "_").replace("-", "_")
    if snake not in aliases and snake != name:
        aliases.append(snake)
    return aliases


# ── Wikilink insertion ──


def insert_wikilinks(
    content: str,
    concept_names: list[str],
    aliases: dict[str, list[str]] | None = None,
) -> str:
    """Insert [[wikilinks]] for first occurrence of each concept in note body.

    Skips frontmatter, code blocks, headings, and already-linked text.
    """
    if not concept_names:
        return content

    name_to_canonical: dict[str, str] = {}
    for cn in concept_names:
        name_to_canonical[cn.lower()] = cn
        if aliases and cn in aliases:
            for a in aliases[cn]:
                name_to_canonical[a.lower()] = cn

    lines = content.split("\n")
    in_frontmatter = False
    in_code_block = False
    linked: set[str] = set()
    result_lines: list[str] = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        if i == 0 and stripped == "---":
            in_frontmatter = True
            result_lines.append(line)
            continue

        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            result_lines.append(line)
            continue

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            result_lines.append(line)
            continue

        if in_code_block:
            result_lines.append(line)
            continue

        if stripped.startswith("#"):
            result_lines.append(line)
            continue

        new_line = line
        for search_term, canonical in sorted(
            name_to_canonical.items(), key=lambda x: -len(x[0])
        ):
            if canonical.lower() in linked:
                continue
            pattern = re.compile(
                r"(?<!\[\[)" + re.escape(search_term) + r"(?!\]\])",
                re.IGNORECASE,
            )
            match = pattern.search(new_line)
            if match:
                original_text = match.group(0)
                new_line = (
                    new_line[: match.start()]
                    + f"[[{canonical}|{original_text}]]"
                    + new_line[match.end() :]
                )
                linked.add(canonical.lower())

        result_lines.append(new_line)

    return "\n".join(result_lines)


# ── INDEX.md generation ──


def generate_index(
    notes_dir: Path,
    concepts: list[ConceptEntry],
    profile: Profile,
    language: Language = Language.EN,
) -> str:
    """Generate INDEX.md content. Pure file operation, no LLM needed."""
    today = date.today().isoformat()

    md_files = sorted(
        (f for f in notes_dir.rglob("*.md")
         if "concepts" not in f.parts
         and "insights" not in f.parts
         and f.name != "INDEX.md"
         and "diagrams" not in f.parts),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    notes_count = len(md_files)

    if language == Language.ZH:
        title = "知识库"
        section_concepts = "概念"
        section_recent = "最近的笔记"
        section_coverage = "覆盖度"
        mastered_label = "已掌握"
        learning_label = "学习中"
        gaps_label = "待学习"
    else:
        title = "Knowledge Base"
        section_concepts = "Concepts"
        section_recent = "Recent Notes"
        section_coverage = "Coverage"
        mastered_label = "mastered"
        learning_label = "learning"
        gaps_label = "gaps"

    header = (
        f"# {title}\n\n"
        f"> {notes_count} notes | {len(concepts)} concepts | Last updated: {today}\n\n"
    )

    known_domains = set()
    for domain_name in profile.skills.domains:
        known_domains.add(domain_name.lower())

    grouped: dict[str, list[ConceptEntry]] = {}
    for c in concepts:
        domain = match_domain(c.name, known_domains)
        grouped.setdefault(domain, []).append(c)

    concepts_section = f"## {section_concepts}\n\n"
    for domain_name in sorted(grouped.keys()):
        concepts_section += f"### {domain_name.replace('_', ' ').title()}\n"
        for c in sorted(grouped[domain_name], key=lambda x: -x.evidence_count):
            stars = _star_rating(c.evidence_count, c.source_notes)
            note_count = len(c.source_notes)
            brief = c.aliases[0] if c.aliases else ""
            concepts_section += (
                f"- [[{c.name}]] {stars} \u2014 {note_count} notes"
            )
            if brief:
                concepts_section += f" \u2014 {brief}"
            concepts_section += "\n"
        concepts_section += "\n"

    recent_section = f"## {section_recent}\n"
    for f in md_files[:10]:
        file_date = _extract_date_from_filename(f.name) or today
        title_text = f.stem.replace("-", " ").title()
        for line in f.read_text(encoding="utf-8").splitlines()[:10]:
            stripped = line.strip()
            if stripped.startswith("# "):
                title_text = stripped[2:].strip()
                break
        recent_section += f"- {file_date}: {title_text}\n"
    recent_section += "\n"

    mastered = sum(1 for c in concepts if c.evidence_count >= 3)
    learning_count = sum(1 for c in concepts if 0 < c.evidence_count < 3)
    gap_count = sum(1 for c in concepts if c.evidence_count == 0)
    coverage_section = (
        f"## {section_coverage}\n"
        f"- {len(concepts)} concepts: "
        f"{mastered} {mastered_label}, "
        f"{learning_count} {learning_label}, "
        f"{gap_count} {gaps_label}\n"
    )

    return header + concepts_section + recent_section + coverage_section


def _star_rating(evidence_count: int, source_notes: list[str]) -> str:
    if evidence_count >= 3:
        return "\u2605\u2605\u2605"
    if evidence_count >= 1:
        return "\u2605\u2605\u2606"
    return "\u2605\u2606\u2606"


def match_domain(concept_name: str, known_domains: set[str]) -> str:
    normalized = concept_name.lower().replace(" ", "_").replace("-", "_")
    for domain in known_domains:
        if domain in normalized or normalized in domain:
            return domain
    return "other"


def _extract_date_from_filename(filename: str) -> str | None:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    return match.group(1) if match else None


# ── Compile cache ──


_NON_SOURCE_DIRS = {"concepts", "insights", "diagrams", "_reports", ".flashcards"}
_NON_SOURCE_FILES = {"INDEX.md", "overview.md", "log.md"}


def collect_compilable_notes(notes_dir: Path) -> list[Path]:
    """Return user-authored notes that may feed concept compilation.

    Generated summaries, reports, indexes, and activity logs must never feed the
    compiler back into itself.  Keeping this filter beside ``compile_all`` also
    gives the CLI, HTTP service, and Daily briefing one source of truth.
    """
    return sorted(
        f for f in notes_dir.rglob("*.md")
        if not _NON_SOURCE_DIRS.intersection(f.relative_to(notes_dir).parts)
        and f.name not in _NON_SOURCE_FILES
    )


class CompileCache:
    """Track compiled note content hashes to avoid reprocessing unchanged notes."""

    def __init__(self, cache_path: Path, notes_root: Path | None = None) -> None:
        self._path = cache_path
        self._notes_root = notes_root.resolve() if notes_root is not None else None
        self._data = self._load()

    def _load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def is_changed(self, note_path: Path) -> bool:
        try:
            content = note_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return True
        current_hash = hashlib.sha256(content.encode()).hexdigest()
        key = self._key(note_path)
        if self._data.get(key) == current_hash:
            return False

        # Compatibility with pre-layout caches that stored absolute paths.  A
        # unique basename + identical content is sufficient to recognize the
        # same note after the whole Neocortex folder (or a topic folder) moves.
        legacy_matches = [
            digest for cached_path, digest in self._data.items()
            if Path(cached_path).name == note_path.name
        ]
        return not (len(legacy_matches) == 1 and legacy_matches[0] == current_hash)

    def update(self, note_path: Path) -> None:
        try:
            content = note_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        self._data[self._key(note_path)] = hashlib.sha256(content.encode()).hexdigest()

    def _key(self, note_path: Path) -> str:
        if self._notes_root is not None:
            try:
                return note_path.resolve().relative_to(self._notes_root).as_posix()
            except ValueError:
                pass
        return str(note_path)

    def save(self) -> None:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._path.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(self._path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


# ── Concept persistence helpers ──


def _load_concept_entry(concepts_dir: Path, name: str) -> ConceptEntry | None:
    slug = name.strip().lower().replace(" ", "-")
    path = concepts_dir / f"{slug}.md"
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8")
    return _parse_concept_frontmatter(content, name)


def _parse_concept_frontmatter(content: str, fallback_name: str) -> ConceptEntry:
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return ConceptEntry(name=fallback_name)

    fm_text = fm_match.group(1)
    entry = ConceptEntry(name=fallback_name)

    for line in fm_text.splitlines():
        if line.startswith("name:"):
            entry.name = line.split(":", 1)[1].strip()
        elif line.startswith("aliases:"):
            raw = line.split(":", 1)[1].strip()
            entry.aliases = _parse_yaml_list_inline(raw)
        elif line.startswith("related_concepts:"):
            raw = line.split(":", 1)[1].strip()
            entry.related_concepts = _parse_yaml_list_inline(raw)
        elif line.startswith("skill_level:"):
            raw = line.split(":", 1)[1].strip()
            try:
                entry.skill_level = SkillLevel(raw)
            except ValueError:
                pass
        elif line.startswith("confidence:"):
            try:
                entry.confidence = float(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("evidence_count:"):
            try:
                entry.evidence_count = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("last_updated:"):
            entry.last_updated = line.split(":", 1)[1].strip()
        elif line.startswith("source_notes:"):
            raw = line.split(":", 1)[1].strip()
            entry.source_notes = _parse_yaml_list_inline(raw)

    return entry


def _parse_yaml_list_inline(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1]
        if not inner.strip():
            return []
        return [item.strip().strip("\"'") for item in inner.split(",") if item.strip()]
    return []


def _save_concept_entry(concepts_dir: Path, name: str, content: str) -> None:
    concepts_dir.mkdir(parents=True, exist_ok=True)
    slug = name.strip().lower().replace(" ", "-")
    path = concepts_dir / f"{slug}.md"
    fd, tmp_path = tempfile.mkstemp(dir=str(concepts_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _update_compiled_clip_status(compiled_files: list[Path]) -> None:
    """Update clip files' status from 'inbox' to 'reference' after compile."""
    for f in compiled_files:
        if "clips" not in f.parts:
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "status: inbox" in content:
            updated = content.replace("status: inbox", "status: reference", 1)
            f.write_text(updated, encoding="utf-8")


def _patch_frontmatter_confidence(content: str, confidence: float, updated: str) -> str:
    """Replace confidence and last_updated values in frontmatter via regex."""
    content = re.sub(
        r"^confidence:\s*[\d.]+",
        f"confidence: {confidence:.4f}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    content = re.sub(
        r"^last_updated:\s*\S+",
        f"last_updated: {updated}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    return content


def collect_all_concepts(concepts_dir: Path) -> list[ConceptEntry]:
    if not concepts_dir.exists():
        return []
    entries: list[ConceptEntry] = []
    for md_file in sorted(concepts_dir.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        entry = _parse_concept_frontmatter(content, md_file.stem)
        entries.append(entry)
    return entries


# ── Semantic related notes ──


def generate_related_notes_block(
    note_path: Path,
    notes_dir: Path,
    max_related: int = 5,
) -> str | None:
    """Use existing fastembed vectors to find related notes.

    Returns a markdown block with related notes sorted by similarity,
    or None if no embeddings are available or no related notes found.
    """
    from neocortex.config import get_data_dir

    db_path = get_data_dir() / "neocortex.sqlite"
    if not db_path.exists():
        return None

    import sqlite3
    try:
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT filename, embedding FROM note_embeddings").fetchall()
        conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return None

    if not rows:
        return None

    try:
        target_filename = str(note_path.relative_to(notes_dir))
    except ValueError:
        target_filename = note_path.name
    target_blob = None
    other_entries: list[tuple[str, bytes]] = []

    for filename, blob in rows:
        if filename == target_filename:
            target_blob = blob
        else:
            other_entries.append((filename, blob))

    if target_blob is None or not other_entries:
        return None

    dim = len(target_blob) // 4
    target_vec = struct.unpack(f"{dim}f", target_blob)
    target_norm = math.sqrt(sum(x * x for x in target_vec))
    if target_norm == 0:
        return None

    similarities: list[tuple[str, float]] = []
    for filename, blob in other_entries:
        other_dim = len(blob) // 4
        if other_dim != dim:
            continue
        other_vec = struct.unpack(f"{other_dim}f", blob)
        dot = sum(a * b for a, b in zip(target_vec, other_vec))
        if dot <= 0:
            continue
        other_norm = math.sqrt(sum(x * x for x in other_vec))
        if other_norm == 0:
            continue
        sim = dot / (target_norm * other_norm)
        if sim > 0.5:
            similarities.append((filename, sim))

    if not similarities:
        return None

    similarities.sort(key=lambda x: -x[1])
    top = similarities[:max_related]

    lines = ["\n---\n\n## Related Notes"]
    for filename, sim in top:
        stem = Path(filename).stem
        lines.append(f"- [[{stem}]] (similarity: {sim:.2f})")
    return "\n".join(lines) + "\n"


# ── Incremental compile ──


async def compile_note(
    note_path: Path,
    notes_dir: Path,
    profile: Profile,
    provider: LLMProvider,
    language: Language = Language.EN,
) -> CompileResult:
    """Incrementally compile a single note: extract concepts, generate/update entries, insert wikilinks."""
    result = CompileResult()

    try:
        content = note_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return result

    concepts = await extract_concepts(content, provider, language)
    if not concepts:
        return result

    result.notes_processed = 1
    concepts_dir = notes_dir / "concepts"

    all_concept_names: list[str] = []
    all_aliases: dict[str, list[str]] = {}

    for ref in concepts:
        display_name = ref.name
        all_concept_names.append(display_name)

        existing = _load_concept_entry(concepts_dir, display_name)

        source_note_info = {
            "filename": note_path.name,
            "title": note_path.stem.replace("-", " "),
            "content_preview": content[:500],
        }

        if existing is not None:
            if note_path.name not in existing.source_notes:
                existing.source_notes.append(note_path.name)
                existing.evidence_count = len(existing.source_notes)
                for rc in ref.related_to:
                    if rc not in existing.related_concepts:
                        existing.related_concepts.append(rc)

                from neocortex.decay import NOTE_BOOST, boost_confidence, decayed_confidence

                current_conf = decayed_confidence(existing.confidence, existing.last_updated)
                existing.last_updated = date.today().isoformat()
                new_conf = boost_confidence(current_conf, NOTE_BOOST)

                source_notes_info = [
                    {"filename": sn, "title": Path(sn).stem.replace("-", " "), "content_preview": ""}
                    for sn in existing.source_notes
                ]
                source_notes_info[-1] = source_note_info

                entry_content = await generate_concept_entry(
                    display_name, source_notes_info,
                    existing.related_concepts, profile, provider, language,
                )
                entry_content = _patch_frontmatter_confidence(
                    entry_content, new_conf, date.today().isoformat(),
                )
                _save_concept_entry(concepts_dir, display_name, entry_content)
                result.concepts_updated += 1
            all_aliases[display_name] = existing.aliases
        else:
            entry_content = await generate_concept_entry(
                display_name, [source_note_info],
                ref.related_to, profile, provider, language,
            )
            _save_concept_entry(concepts_dir, display_name, entry_content)
            result.concepts_created += 1
            all_aliases[display_name] = _generate_aliases(display_name)

    try:
        claims = await extract_claims(content, provider, language)
        if claims:
            from neocortex.config import load_claims, save_claims

            all_claims = load_claims()

            try:
                conflicts = await detect_conflicts(claims, all_claims, provider, language)
                if conflicts:
                    for conflict in conflicts:
                        conflict["source_b"] = note_path.name
                    result.conflicts = conflicts

                    from neocortex.config import load_belief_changes, save_belief_changes

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
                    if belief_changes:
                        save_belief_changes(belief_changes)
            except Exception:
                pass

            for c in claims:
                concept_name = normalize_gap_name(c.get("concept", ""))
                if not concept_name:
                    continue
                all_claims.setdefault(concept_name, []).append({
                    "claim": c["claim"],
                    "source": note_path.name,
                    "date": date.today().isoformat(),
                    "context": c.get("context", ""),
                })
            save_claims(all_claims)
    except Exception:
        pass

    new_content = insert_wikilinks(content, all_concept_names, all_aliases)

    related_block = generate_related_notes_block(note_path, notes_dir)
    if related_block:
        existing_related = re.search(r"\n---\s*\n\s*## Related Notes\b.*", new_content, re.DOTALL)
        if existing_related:
            new_content = new_content[:existing_related.start()] + related_block
        else:
            new_content = new_content.rstrip("\n") + "\n" + related_block

    if new_content != content:
        result.wikilinks_inserted = new_content.count("[[") - content.count("[[")
        note_path.write_text(new_content, encoding="utf-8")

    await _generate_relationship_cards(notes_dir, concepts, provider, language)

    # Ripple: update related_notes blocks in notes that share concepts
    _ripple_related_notes(note_path, notes_dir, concepts)

    all_concepts = collect_all_concepts(concepts_dir)
    index_content = generate_index(notes_dir, all_concepts, profile, language)
    index_path = notes_dir / "INDEX.md"
    fd, tmp_path = tempfile.mkstemp(dir=str(notes_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(index_content)
        os.replace(tmp_path, str(index_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    result.index_updated = True

    return result


# ── Ripple effect ──


def _ripple_related_notes(
    new_note: Path,
    notes_dir: Path,
    concepts: list[ConceptRef],
    max_updates: int = 5,
) -> int:
    """Update related_notes blocks in existing notes that share concepts with the new note.

    Returns the number of notes updated.
    """
    concepts_dir = notes_dir / "concepts"
    if not concepts_dir.exists():
        return 0

    # Collect all note filenames that share concepts with the new note
    sibling_files: set[str] = set()
    for ref in concepts:
        entry = _load_concept_entry(concepts_dir, ref.name)
        if entry:
            for sn in entry.source_notes:
                if sn != new_note.name:
                    sibling_files.add(sn)

    if not sibling_files:
        return 0

    # Find actual file paths for siblings
    all_md = {f.name: f for f in notes_dir.rglob("*.md")
              if "concepts" not in f.parts and "insights" not in f.parts
              and f.name != "INDEX.md" and f.name != "overview.md"
              and "diagrams" not in f.parts and "_reports" not in f.parts}

    updated = 0
    for sib_name in list(sibling_files)[:max_updates]:
        sib_path = all_md.get(sib_name)
        if not sib_path or not sib_path.exists():
            continue

        new_block = generate_related_notes_block(sib_path, notes_dir)
        if not new_block:
            continue

        try:
            content = sib_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        existing_related = re.search(r"\n---\s*\n\s*## Related Notes\b.*", content, re.DOTALL)
        if existing_related:
            new_content = content[:existing_related.start()] + new_block
        else:
            new_content = content.rstrip("\n") + "\n" + new_block

        if new_content != content:
            sib_path.write_text(new_content, encoding="utf-8")
            updated += 1

    return updated


# ── Relationship cards ──


async def _generate_relationship_cards(
    notes_dir: Path,
    concepts: list[ConceptRef],
    provider: LLMProvider,
    language: Language,
) -> None:
    """Generate relationship cards for concept pairs with evidence_count >= 2."""
    from neocortex.config import load_flashcards

    concepts_dir = notes_dir / "concepts"

    eligible = []
    for ref in concepts:
        existing = _load_concept_entry(concepts_dir, ref.name)
        if existing and existing.evidence_count >= 2:
            eligible.append(existing)

    if len(eligible) < 2:
        return

    pairs: list[tuple[str, str]] = []
    for c in eligible:
        for rel_name in c.related_concepts:
            for other in eligible:
                if other.name == rel_name:
                    pair = tuple(sorted([c.name, other.name]))
                    if pair not in pairs:
                        pairs.append(pair)

    if not pairs:
        return

    all_cards = load_flashcards(notes_dir)
    existing_pairs = set()
    for fc in all_cards:
        if fc.card_type == "relationship":
            existing_pairs.add(fc.concept)

    new_pairs = [p for p in pairs if f"{p[0]} <> {p[1]}" not in existing_pairs]
    if not new_pairs:
        return

    for batch_pairs in [new_pairs[i:i + 3] for i in range(0, len(new_pairs), 3)]:
        await _generate_relationship_batch(notes_dir, batch_pairs, provider, language)


async def _generate_relationship_batch(
    notes_dir: Path,
    pairs: list[tuple[str, str]],
    provider: LLMProvider,
    language: Language,
) -> None:
    """Generate relationship flashcards for a batch of concept pairs."""
    import uuid

    from neocortex.models import Flashcard

    lang_inst = "\u7528\u4e2d\u6587\u8f93\u51fa\u3002" if language == Language.ZH else "Output in English."

    pairs_text = "\n".join(f"- {a} \u2194 {b}" for a, b in pairs)

    prompt = f"""Generate relationship flashcards that test the CONNECTION between concept pairs.

Concept pairs:
{pairs_text}

For each pair, generate 1 flashcard:
- question: Test why/how these concepts relate (not just definitions)
- answer: Concise explanation of the relationship (2-3 sentences)
- concept_a: First concept name
- concept_b: Second concept name

Output JSON array:
[{{"question": "...", "answer": "...", "concept_a": "...", "concept_b": "..."}}]

{lang_inst}"""

    try:
        raw = await provider.chat([{"role": "user", "content": prompt}], json_mode=True)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        return

    if not isinstance(data, list):
        return

    cards: list[Flashcard] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        q = item.get("question", "")
        a = item.get("answer", "")
        ca = item.get("concept_a", "")
        cb = item.get("concept_b", "")
        if q and a and ca and cb:
            pair_label = " <> ".join(sorted([ca, cb]))
            cards.append(Flashcard(
                id=str(uuid.uuid4())[:8],
                source_note="",
                question=q,
                answer=a,
                concept=pair_label,
                difficulty="medium",
                knowledge_layer="conceptual",
                card_type="relationship",
                next_review=date.today().isoformat(),
            ))

    if cards:
        # 读-改-写全程持复习写锁：GUI/CLI 评分会并发更新同一文件，不持锁
        # 的话这里的整文件覆写会吃掉刚落盘的 SM-2 进度（最后写入者获胜）。
        # 原始条目（包括当前模型解析不了的坏条目）原样保留，只追加新卡。
        from neocortex.services.review import atomic_save_raw, review_write_lock

        rel_path = notes_dir / ".flashcards" / "_relationships.json"
        rel_path.parent.mkdir(parents=True, exist_ok=True)
        with review_write_lock(notes_dir):
            raw_items: list = []
            if rel_path.exists():
                try:
                    raw_data = json.loads(rel_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    raw_data = None
                if isinstance(raw_data, list):
                    raw_items = raw_data
            raw_items.extend(c.model_dump(mode="json") for c in cards)
            atomic_save_raw(rel_path, raw_items)


# ── Full compile ──


async def compile_all(
    notes_dir: Path,
    profile: Profile,
    provider: LLMProvider,
    language: Language = Language.EN,
    on_progress: Callable[[int, int], None] | None = None,
    force: bool = False,
) -> CompileResult:
    """Compile all notes in the notes directory."""
    from neocortex.config import get_data_dir

    result = CompileResult()

    md_files = collect_compilable_notes(notes_dir)

    if not md_files:
        return result

    cache_path = get_data_dir() / "compile_cache.json"
    cache = CompileCache(cache_path, notes_root=notes_dir)

    changed_files: list[Path] = []
    for f in md_files:
        if force or cache.is_changed(f):
            changed_files.append(f)

    if not changed_files:
        return result

    concepts_dir = notes_dir / "concepts"
    all_concept_names: list[str] = []
    seen_normalized: set[str] = set()
    all_aliases: dict[str, list[str]] = {}
    note_concepts_map: dict[str, list[ConceptRef]] = {}

    total = len(changed_files)
    for idx, note_path in enumerate(changed_files):
        if on_progress:
            on_progress(idx + 1, total)

        try:
            content = note_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        concepts = await extract_concepts(content, provider, language)
        if concepts:
            note_concepts_map[str(note_path)] = concepts
            result.notes_processed += 1

    for note_path_str, concepts in note_concepts_map.items():
        note_path = Path(note_path_str)
        try:
            content = note_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for ref in concepts:
            display_name = ref.name
            normalized = normalize_gap_name(display_name)
            if normalized not in seen_normalized:
                all_concept_names.append(display_name)
                seen_normalized.add(normalized)

            existing = _load_concept_entry(concepts_dir, display_name)
            source_note_info = {
                "filename": note_path.name,
                "title": note_path.stem.replace("-", " "),
                "content_preview": content[:500],
            }

            if existing is not None:
                if note_path.name not in existing.source_notes:
                    existing.source_notes.append(note_path.name)
                    existing.evidence_count = len(existing.source_notes)
                    for rc in ref.related_to:
                        if rc not in existing.related_concepts:
                            existing.related_concepts.append(rc)

                    from neocortex.decay import NOTE_BOOST, boost_confidence, decayed_confidence

                    current_conf = decayed_confidence(existing.confidence, existing.last_updated)
                    existing.last_updated = date.today().isoformat()
                    new_conf = boost_confidence(current_conf, NOTE_BOOST)

                    source_notes_info = [
                        {"filename": sn, "title": Path(sn).stem.replace("-", " "), "content_preview": ""}
                        for sn in existing.source_notes
                    ]
                    source_notes_info[-1] = source_note_info

                    entry_content = await generate_concept_entry(
                        display_name, source_notes_info,
                        existing.related_concepts, profile, provider, language,
                    )
                    entry_content = _patch_frontmatter_confidence(
                        entry_content, new_conf, date.today().isoformat(),
                    )
                    _save_concept_entry(concepts_dir, display_name, entry_content)
                    result.concepts_updated += 1
                all_aliases[display_name] = existing.aliases
            else:
                entry_content = await generate_concept_entry(
                    display_name, [source_note_info],
                    ref.related_to, profile, provider, language,
                )
                _save_concept_entry(concepts_dir, display_name, entry_content)
                result.concepts_created += 1
                all_aliases[display_name] = _generate_aliases(display_name)

    for note_path_str in note_concepts_map:
        note_path = Path(note_path_str)
        try:
            content = note_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        new_content = insert_wikilinks(content, all_concept_names, all_aliases)
        if new_content != content:
            result.wikilinks_inserted += new_content.count("[[") - content.count("[[")
            note_path.write_text(new_content, encoding="utf-8")

        cache.update(note_path)

    cache.save()

    # Mark compiled clips as "reference" (no longer inbox)
    _update_compiled_clip_status(changed_files)

    all_concepts = collect_all_concepts(concepts_dir)
    index_content = generate_index(notes_dir, all_concepts, profile, language)
    index_path = notes_dir / "INDEX.md"
    fd, tmp_path = tempfile.mkstemp(dir=str(notes_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(index_content)
        os.replace(tmp_path, str(index_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    result.index_updated = True

    # Rebuild search index so new content is immediately searchable
    try:
        from neocortex.search import NoteIndex
        search_index = NoteIndex(notes_dir / ".search.db")
        search_index.index_all(notes_dir)
    except Exception as exc:
        from neocortex.i18n import t
        result.warnings.append(t("compile_search_index_failed", language, error=str(exc) or exc.__class__.__name__))

    # Generate overview.md — narrative synthesis of the entire knowledge base
    try:
        await generate_overview(notes_dir, all_concepts, profile, provider, language)
    except Exception as exc:
        from neocortex.i18n import t
        result.warnings.append(t("compile_overview_failed", language, error=str(exc) or exc.__class__.__name__))

    return result


# ── Overview generation ──


async def generate_overview(
    notes_dir: Path,
    concepts: list[ConceptEntry],
    profile: Profile,
    provider: LLMProvider,
    language: Language = Language.EN,
) -> None:
    """Generate overview.md — a narrative synthesis of the knowledge base."""
    if not concepts:
        return

    # Build context for LLM
    concept_summary = []
    for c in sorted(concepts, key=lambda x: -x.evidence_count):
        concept_summary.append(
            f"- {c.name} (evidence: {c.evidence_count}, confidence: {c.confidence:.2f}, "
            f"sources: {len(c.source_notes)}, related: {', '.join(c.related_concepts[:3])})"
        )
    concepts_text = "\n".join(concept_summary[:40])

    # Profile gaps
    gap_list: list[str] = []
    for d in profile.skills.domains.values():
        gap_list.extend(d.gaps)
    gaps_text = ", ".join(gap_list[:20]) if gap_list else "(none)"

    # Recent belief changes
    belief_text = ""
    try:
        from neocortex.config import load_belief_changes
        changes = load_belief_changes()
        if changes:
            recent = changes[-5:]
            belief_lines = []
            for ch in recent:
                belief_lines.append(
                    f"- [{ch.get('date', '?')}] {ch.get('concept', '?')}: "
                    f"'{ch.get('from', '')[:60]}' → '{ch.get('to', '')[:60]}'"
                )
            belief_text = "\n".join(belief_lines)
    except Exception:
        pass

    # Recent log entries
    log_text = ""
    log_path = notes_dir / "log.md"
    if log_path.exists():
        try:
            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            log_text = "\n".join(lines[-20:])
        except (OSError, UnicodeDecodeError):
            pass

    lang_inst = "用中文写作。" if language == Language.ZH else "Write in English."
    if language == Language.ZH:
        sections = "## 知识地图\n## 跨领域连接\n## 信念演变\n## 盲区提示\n## 建议方向"
    else:
        sections = "## Knowledge Map\n## Cross-Domain Connections\n## Belief Evolution\n## Blind Spots\n## Suggested Directions"

    messages = [
        {
            "role": "system",
            "content": (
                "You generate a narrative overview of a developer's personal knowledge base. "
                "This is NOT an index — it is a thoughtful synthesis of what the knowledge "
                "base reveals about the user's learning journey. Be specific, reference "
                "actual concepts and connections. Be concise — each section 2-4 sentences.\n\n"
                f"Generate these sections:\n{sections}\n\n{lang_inst}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Concepts ({len(concepts)} total):\n{concepts_text}\n\n"
                f"Skill gaps: {gaps_text}\n\n"
                f"Recent belief changes:\n{belief_text or '(none)'}\n\n"
                f"Recent activity:\n{log_text or '(none)'}"
            ),
        },
    ]

    body = await provider.chat(messages)

    today = date.today().isoformat()
    content = (
        f"---\ntype: overview\ndate: {today}\nconcepts: {len(concepts)}\n---\n\n"
        f"# Overview\n\n"
        f"> Auto-generated on {today} from {len(concepts)} concepts.\n\n"
        f"{body}\n"
    )

    overview_path = notes_dir / "overview.md"
    fd, tmp_path = tempfile.mkstemp(dir=str(notes_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(overview_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
