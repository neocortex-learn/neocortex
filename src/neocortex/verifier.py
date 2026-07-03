"""Knowledge base fidelity verification engine.

Verifies that LLM-compiled concept entries are faithful to source notes.
Follows the Hermes isolation principle: the reviewer never sees the generation
process — only the generated artifact and raw source material.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path

from neocortex.llm.base import LLMProvider
from neocortex.models import (
    AtomicFact,
    ConceptEntry,
    ConceptVerification,
    Evidence,
    FactCheck,
    FactVerdict,
    Language,
    VerifyReport,
)


# ── Helpers ──


def _strip_json_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return raw


def _parse_json_array(raw: str) -> list[dict]:
    raw = _strip_json_fences(raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def extract_concept_body(concept_content: str) -> str:
    """Extract the LLM-generated body from a concept entry.

    Strips frontmatter, the top-level heading, Source Notes section,
    and Related Concepts section.
    """
    lines = concept_content.split("\n")
    result: list[str] = []
    in_frontmatter = False
    skip_section = False

    # Section headings to skip (LLM didn't generate these)
    skip_headings = {
        "source notes", "来源笔记",
        "related concepts", "关联概念",
        "related notes", "相关笔记",
    }

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Handle frontmatter
        if i == 0 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue

        # Skip top-level heading (# Concept Name)
        if stripped.startswith("# ") and not stripped.startswith("## "):
            continue

        # Check if entering a section to skip
        if stripped.startswith("## "):
            heading_text = stripped.lstrip("#").strip().lower()
            skip_section = heading_text in skip_headings
            if skip_section:
                continue

        if skip_section:
            # Stop skipping when a new section starts
            if stripped.startswith("## "):
                heading_text = stripped.lstrip("#").strip().lower()
                skip_section = heading_text in skip_headings
                if skip_section:
                    continue
                else:
                    skip_section = False
            else:
                continue

        result.append(line)

    return "\n".join(result).strip()


# ── Stage 1: Atomic Fact Decomposition ──


async def decompose_atomic_facts(
    concept_body: str,
    concept_name: str,
    provider: LLMProvider,
    language: Language = Language.EN,
) -> list[AtomicFact]:
    """Decompose concept entry body into atomic verifiable facts."""
    if not concept_body.strip():
        return []

    lang_instruction = "用中文输出。" if language == Language.ZH else "Respond in English."

    messages = [
        {
            "role": "system",
            "content": (
                "You decompose a concept wiki entry into atomic, verifiable factual claims. "
                "Rules: "
                "1. Each claim must be self-contained (replace pronouns with entity names). "
                "2. Skip rhetorical questions, section headers, and meta-information. "
                "3. Skip hedged statements ('may', 'could', 'possibly'). "
                "4. Extract 3-8 claims maximum. "
                "5. Each claim is a single factual assertion. "
                f"{lang_instruction} "
                'Output ONLY a JSON array: [{"fact": "...", "section": "..."}]'
            ),
        },
        {
            "role": "user",
            "content": f"Concept: {concept_name}\n\n{concept_body[:3000]}",
        },
    ]

    raw = await provider.chat(messages, json_mode=True)
    data = _parse_json_array(raw)

    facts: list[AtomicFact] = []
    for item in data:
        if "fact" not in item:
            continue
        facts.append(AtomicFact(
            text=item["fact"],
            section=item.get("section", ""),
            concept=concept_name,
        ))

    return facts[:8]


# ── Stage 2: Source Grounding (keyword matching, zero LLM cost) ──


_STOP_WORDS_EN = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "and", "or", "but",
    "not", "no", "nor", "so", "yet", "both", "either", "neither", "each",
    "every", "all", "any", "few", "more", "most", "other", "some", "such",
    "than", "too", "very", "just", "also", "that", "this", "these", "those",
    "it", "its", "they", "them", "their", "which", "what", "when", "where",
    "who", "how", "why", "if", "then", "only", "same", "about", "up",
    "out", "over", "under", "again", "further", "once",
}

_STOP_CHARS_ZH = set(
    "的了在是和与或等及对中为以将把被从到而但也还就都不没有可以这那一个"
    "其它他她它们我你您他们我们你们自己所着过地得很更最能会要让使"
)


def _extract_keywords(text: str) -> list[str]:
    """Extract significant keywords from a fact for matching.

    For Chinese: split into bigrams (2-char sliding window) after removing
    stop characters and punctuation, producing overlapping 2-char terms.
    For English: split on whitespace/punctuation, remove stop words.
    """
    # Separate Chinese and English parts
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    english_words = re.findall(r"[a-zA-Z]{2,}", text.lower())

    keywords: list[str] = []

    # English keywords
    for w in english_words:
        if w not in _STOP_WORDS_EN:
            keywords.append(w)

    # Chinese keywords: filter stop chars, then extract bigrams
    filtered_zh = [c for c in chinese_chars if c not in _STOP_CHARS_ZH]
    for i in range(len(filtered_zh) - 1):
        bigram = filtered_zh[i] + filtered_zh[i + 1]
        keywords.append(bigram)

    return keywords


def find_evidence_keyword(
    fact: AtomicFact,
    source_contents: dict[str, str],
) -> list[Evidence]:
    """Find supporting evidence via keyword matching. Zero LLM cost."""
    keywords = _extract_keywords(fact.text)
    if not keywords:
        return []

    evidence: list[Evidence] = []

    for filename, content in source_contents.items():
        content_lower = content.lower()
        # Count how many keywords appear in this source
        matched = [kw for kw in keywords if kw in content_lower]
        if len(matched) < max(2, len(keywords) // 2):
            continue

        # Find the best matching paragraph
        paragraphs = re.split(r"\n\s*\n", content)
        best_para = ""
        best_score = 0

        for para in paragraphs:
            para_lower = para.lower()
            score = sum(1 for kw in keywords if kw in para_lower)
            if score > best_score:
                best_score = score
                best_para = para

        if best_para:
            evidence.append(Evidence(
                source_note=filename,
                excerpt=best_para[:500],
                matched_by="keyword",
            ))

    return evidence


# ── Stage 3: Verdict Assignment ──


async def assign_verdicts(
    fact_evidence_pairs: list[tuple[AtomicFact, list[Evidence]]],
    provider: LLMProvider,
    language: Language = Language.EN,
) -> list[FactCheck]:
    """Batch-judge all facts for a single concept in one LLM call.

    Follows Hermes isolation: prompt explicitly states the reviewer
    did NOT generate these claims.
    """
    if not fact_evidence_pairs:
        return []

    lang_instruction = "用中文输出解释。" if language == Language.ZH else "Respond in English for explanations."

    # Build the batch prompt
    items_text = ""
    for i, (fact, evidences) in enumerate(fact_evidence_pairs):
        evidence_text = ""
        if evidences:
            for ev in evidences:
                evidence_text += f"  [{ev.source_note}]: {ev.excerpt}\n"
        else:
            evidence_text = "  (no matching source text found)\n"

        items_text += (
            f"Claim {i}: {fact.text}\n"
            f"Source excerpts:\n{evidence_text}\n"
        )

    messages = [
        {
            "role": "system",
            "content": (
                "You are an independent fact-checker for a personal knowledge wiki. "
                "You did NOT generate these claims — you are verifying them against source notes. "
                "For each claim, the source text excerpts are provided. Judge each as:\n"
                "- SUPPORTED: The source text clearly states or directly implies this claim\n"
                "- UNSUPPORTED: The source text contradicts this, or the claim appears fabricated\n"
                "- UNVERIFIABLE: The source text is related but insufficient to confirm or deny\n\n"
                "Be strict: if the claim adds specificity not present in sources "
                "(exact numbers, absolute statements, causal claims), mark as UNSUPPORTED "
                "unless sources match exactly.\n\n"
                f"{lang_instruction} "
                'Output ONLY a JSON array: [{"index": 0, "verdict": "supported|unsupported|unverifiable", "explanation": "..."}]'
            ),
        },
        {
            "role": "user",
            "content": items_text,
        },
    ]

    raw = await provider.chat(messages, json_mode=True)
    data = _parse_json_array(raw)

    verdict_map = {
        "supported": FactVerdict.SUPPORTED,
        "unsupported": FactVerdict.UNSUPPORTED,
        "unverifiable": FactVerdict.UNVERIFIABLE,
    }

    results: list[FactCheck] = []
    # Build index-based lookup for LLM results
    llm_verdicts: dict[int, dict] = {}
    for item in data:
        idx = item.get("index", -1)
        if isinstance(idx, int) and 0 <= idx < len(fact_evidence_pairs):
            llm_verdicts[idx] = item

    for i, (fact, evidences) in enumerate(fact_evidence_pairs):
        if i in llm_verdicts:
            v = llm_verdicts[i]
            verdict = verdict_map.get(
                v.get("verdict", "").lower(),
                FactVerdict.UNVERIFIABLE,
            )
            explanation = v.get("explanation", "")
        else:
            verdict = FactVerdict.UNVERIFIABLE
            explanation = "LLM did not return a verdict for this claim."

        results.append(FactCheck(
            fact=fact,
            verdict=verdict,
            evidence=evidences,
            explanation=explanation,
        ))

    return results


# ── Concept-level verification ──


def _load_concept_meta(concept_path: Path) -> ConceptEntry | None:
    """Parse frontmatter from a concept file into ConceptEntry."""
    try:
        content = concept_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return None

    fm = fm_match.group(1)
    entry = ConceptEntry(name=concept_path.stem)

    for line in fm.splitlines():
        if line.startswith("name:"):
            entry.name = line.split(":", 1)[1].strip()
        elif line.startswith("source_notes:"):
            raw = line.split(":", 1)[1].strip()
            if raw.startswith("[") and raw.endswith("]"):
                inner = raw[1:-1]
                if inner.strip():
                    entry.source_notes = [
                        s.strip().strip("\"'") for s in inner.split(",") if s.strip()
                    ]
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

    return entry


async def verify_concept(
    concept_entry: ConceptEntry,
    concept_content: str,
    source_contents: dict[str, str],
    provider: LLMProvider | None,
    language: Language = Language.EN,
    depth: str = "standard",
) -> ConceptVerification:
    """Full verification pipeline for a single concept entry."""
    body = extract_concept_body(concept_content)
    result = ConceptVerification(concept_name=concept_entry.name)

    if not body.strip():
        return result

    # Stage 1: Decompose into atomic facts
    if depth == "shallow":
        # In shallow mode, use concept name as a simple fact (no LLM)
        # Just check if source notes mention the concept
        keywords = _extract_keywords(concept_entry.name)
        has_evidence = False
        for content in source_contents.values():
            if all(kw in content.lower() for kw in keywords):
                has_evidence = True
                break
        if has_evidence:
            result.supported_count = 1
        else:
            result.unverifiable_count = 1
        result.fact_checks = [FactCheck(
            fact=AtomicFact(text=concept_entry.name, concept=concept_entry.name),
            verdict=FactVerdict.SUPPORTED if has_evidence else FactVerdict.UNVERIFIABLE,
        )]
        return result

    assert provider is not None, "LLM provider required for standard/deep verification"
    facts = await decompose_atomic_facts(body, concept_entry.name, provider, language)
    if not facts:
        return result

    # Stage 2: Find evidence via keyword matching
    fact_evidence_pairs: list[tuple[AtomicFact, list[Evidence]]] = []
    for fact in facts:
        evidence = find_evidence_keyword(fact, source_contents)
        fact_evidence_pairs.append((fact, evidence))

    # Stage 3: LLM verdict assignment
    checks = await assign_verdicts(fact_evidence_pairs, provider, language)

    # Aggregate
    result.fact_checks = checks
    for check in checks:
        if check.verdict == FactVerdict.SUPPORTED:
            result.supported_count += 1
        elif check.verdict == FactVerdict.UNSUPPORTED:
            result.unsupported_count += 1
        else:
            result.unverifiable_count += 1

    return result


# ── Overview verification ──


async def verify_overview(
    overview_content: str,
    concept_names: list[str],
    provider: LLMProvider,
    language: Language = Language.EN,
) -> list[FactCheck]:
    """Verify overview.md cross-concept claims against concept entries."""
    body = extract_concept_body(overview_content)
    if not body.strip():
        return []

    # Decompose overview into atomic facts
    lang_instruction = "用中文输出。" if language == Language.ZH else "Respond in English."

    messages = [
        {
            "role": "system",
            "content": (
                "You decompose a knowledge base overview into atomic factual claims "
                "about concept relationships and learning patterns. "
                "Rules: "
                "1. Each claim must be self-contained. "
                "2. Focus on cross-concept assertions (e.g. 'X and Y are connected because...'). "
                "3. Skip vague or hedged statements. "
                "4. Extract 3-6 claims maximum. "
                f"{lang_instruction} "
                'Output ONLY a JSON array: [{"fact": "...", "section": "..."}]'
            ),
        },
        {
            "role": "user",
            "content": body[:3000],
        },
    ]

    raw = await provider.chat(messages, json_mode=True)
    data = _parse_json_array(raw)

    facts: list[AtomicFact] = []
    for item in data:
        if "fact" not in item:
            continue
        facts.append(AtomicFact(
            text=item["fact"],
            section=item.get("section", ""),
            concept="overview",
        ))

    if not facts:
        return []

    # Check each fact: do the mentioned concepts actually exist?
    messages_verify = [
        {
            "role": "system",
            "content": (
                "You are verifying whether claims about concept relationships are grounded. "
                "For each claim, check if the concepts it references exist in the provided concept list. "
                "If both concepts exist, mark SUPPORTED. If a concept is mentioned but doesn't exist, "
                "mark UNSUPPORTED. If unclear, mark UNVERIFIABLE.\n"
                f"Available concepts: {', '.join(sorted(concept_names)[:40])}\n\n"
                f"{lang_instruction} "
                'Output ONLY a JSON array: [{"index": 0, "verdict": "supported|unsupported|unverifiable", "explanation": "..."}]'
            ),
        },
        {
            "role": "user",
            "content": "\n".join(f"Claim {i}: {f.text}" for i, f in enumerate(facts)),
        },
    ]

    raw = await provider.chat(messages_verify, json_mode=True)
    verdicts_data = _parse_json_array(raw)

    verdict_map = {
        "supported": FactVerdict.SUPPORTED,
        "unsupported": FactVerdict.UNSUPPORTED,
        "unverifiable": FactVerdict.UNVERIFIABLE,
    }

    checks: list[FactCheck] = []
    llm_verdicts: dict[int, dict] = {}
    for item in verdicts_data:
        idx = item.get("index", -1)
        if isinstance(idx, int) and 0 <= idx < len(facts):
            llm_verdicts[idx] = item

    for i, fact in enumerate(facts):
        if i in llm_verdicts:
            v = llm_verdicts[i]
            verdict = verdict_map.get(v.get("verdict", "").lower(), FactVerdict.UNVERIFIABLE)
            explanation = v.get("explanation", "")
        else:
            verdict = FactVerdict.UNVERIFIABLE
            explanation = ""

        checks.append(FactCheck(fact=fact, verdict=verdict, explanation=explanation))

    return checks


# ── Claims cross-verification ──


async def cross_verify_claims(
    concept_name: str,
    concept_body: str,
    stored_claims: list[dict],
    provider: LLMProvider,
    language: Language = Language.EN,
) -> list[FactCheck]:
    """Compare stored claims (from compile) against concept entry content.

    Checks whether claims extracted during compile are consistent with
    the final concept entry. Detects drift between claims.json and
    the actual concept page.
    """
    if not stored_claims or not concept_body.strip():
        return []

    lang_instruction = "用中文输出。" if language == Language.ZH else "Respond in English."

    claims_text = "\n".join(
        f"Claim {i}: {c['claim']}" for i, c in enumerate(stored_claims)
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are comparing stored factual claims against a concept wiki entry. "
                "For each claim, check if the concept entry's content is consistent with it. "
                "Judge each as:\n"
                "- CONSISTENT: The concept entry agrees with or includes this claim\n"
                "- DRIFTED: The concept entry contradicts or significantly reframes this claim\n"
                "- ABSENT: The concept entry does not mention this claim at all\n\n"
                f"{lang_instruction} "
                'Output ONLY a JSON array: [{"index": 0, "verdict": "consistent|drifted|absent", "explanation": "..."}]'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Concept entry for '{concept_name}':\n{concept_body[:2000]}\n\n"
                f"Stored claims:\n{claims_text}"
            ),
        },
    ]

    raw = await provider.chat(messages, json_mode=True)
    data = _parse_json_array(raw)

    verdict_map = {
        "consistent": FactVerdict.SUPPORTED,
        "drifted": FactVerdict.UNSUPPORTED,
        "absent": FactVerdict.UNVERIFIABLE,
    }

    checks: list[FactCheck] = []
    llm_verdicts: dict[int, dict] = {}
    for item in data:
        idx = item.get("index", -1)
        if isinstance(idx, int) and 0 <= idx < len(stored_claims):
            llm_verdicts[idx] = item

    for i, claim in enumerate(stored_claims):
        fact = AtomicFact(
            text=claim["claim"],
            section="claims.json",
            concept=concept_name,
        )
        if i in llm_verdicts:
            v = llm_verdicts[i]
            verdict = verdict_map.get(v.get("verdict", "").lower(), FactVerdict.UNVERIFIABLE)
            explanation = v.get("explanation", "")
        else:
            verdict = FactVerdict.UNVERIFIABLE
            explanation = ""
        checks.append(FactCheck(fact=fact, verdict=verdict, explanation=explanation))

    return checks


# ── Self-consistency check ──


async def self_consistency_check(
    concept_body: str,
    concept_name: str,
    provider: LLMProvider,
    language: Language = Language.EN,
    n_samples: int = 3,
) -> list[FactCheck]:
    """SelfCheckGPT-inspired: ask the LLM to summarize the same concept
    multiple times and check if key assertions are consistent across samples.

    Returns FactChecks for assertions that are inconsistent across samples.
    """
    if not concept_body.strip():
        return []

    lang_instruction = "用中文输出。" if language == Language.ZH else "Respond in English."

    # Step 1: Extract key assertions from the concept entry
    messages_extract = [
        {
            "role": "system",
            "content": (
                "Extract the 3-5 most important factual assertions from this concept entry. "
                "Each assertion should be a specific, verifiable claim. "
                f"{lang_instruction} "
                'Output ONLY a JSON array: [{"assertion": "..."}]'
            ),
        },
        {"role": "user", "content": f"Concept: {concept_name}\n\n{concept_body[:2000]}"},
    ]

    raw = await provider.chat(messages_extract, json_mode=True)
    assertions_data = _parse_json_array(raw)
    assertions = [a["assertion"] for a in assertions_data if "assertion" in a][:5]

    if not assertions:
        return []

    # Step 2: Ask the LLM to independently assess each assertion N times
    # If the LLM "knows" the fact, answers converge; if hallucinated, they diverge
    assertions_text = "\n".join(f"{i + 1}. {a}" for i, a in enumerate(assertions))

    import asyncio as _aio

    async def _sample_once() -> list[str]:
        messages_check = [
            {
                "role": "system",
                "content": (
                    "For each assertion below, respond with TRUE if it is a well-known, "
                    "generally accepted fact, or FALSE if it seems incorrect, fabricated, "
                    "or highly specific/unverifiable. "
                    'Output ONLY a JSON array: [{"index": 1, "verdict": "true|false"}]'
                ),
            },
            {"role": "user", "content": assertions_text},
        ]
        raw = await provider.chat(messages_check, json_mode=True)
        verdicts = _parse_json_array(raw)

        sample_verdicts: list[str] = ["unknown"] * len(assertions)
        for v in verdicts:
            idx = v.get("index", -1)
            # Accept both 0-indexed and 1-indexed responses
            if isinstance(idx, int):
                if 1 <= idx <= len(assertions):
                    sample_verdicts[idx - 1] = v.get("verdict", "unknown").lower()
                elif idx == 0:
                    sample_verdicts[0] = v.get("verdict", "unknown").lower()
        return sample_verdicts

    samples = await _aio.gather(*[_sample_once() for _ in range(n_samples)])

    # Step 3: Check consistency — if any assertion gets mixed true/false, flag it
    checks: list[FactCheck] = []
    for i, assertion in enumerate(assertions):
        verdicts_for_i = [s[i] for s in samples]
        true_count = sum(1 for v in verdicts_for_i if v == "true")
        false_count = sum(1 for v in verdicts_for_i if v == "false")

        fact = AtomicFact(text=assertion, section="self-consistency", concept=concept_name)

        if true_count == n_samples:
            verdict = FactVerdict.SUPPORTED
            explanation = f"Consistent across {n_samples} samples (all TRUE)"
        elif false_count == n_samples:
            verdict = FactVerdict.UNSUPPORTED
            explanation = f"Consistent across {n_samples} samples (all FALSE)"
        else:
            verdict = FactVerdict.UNVERIFIABLE
            explanation = f"Inconsistent: {true_count} TRUE, {false_count} FALSE out of {n_samples} samples"

        checks.append(FactCheck(fact=fact, verdict=verdict, explanation=explanation))

    return checks


# ── Cache ──


class VerifyCache:
    """Track verified concept content hashes to skip re-verification."""

    def __init__(self, cache_path: Path) -> None:
        self._path = cache_path
        self._data = self._load()

    def _load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def needs_verify(self, concept_path: Path) -> bool:
        try:
            content = concept_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return True
        current_hash = hashlib.sha256(content.encode()).hexdigest()
        return self._data.get(str(concept_path)) != current_hash

    def mark_verified(self, concept_path: Path) -> None:
        try:
            content = concept_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        self._data[str(concept_path)] = hashlib.sha256(content.encode()).hexdigest()

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
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


# ── Confidence update ──


def update_concept_confidence(concept_path: Path, verification: ConceptVerification) -> None:
    """Lower confidence for concepts with unsupported facts.

    - supported_ratio >= 0.8: no change
    - supported_ratio < 0.8: confidence *= 0.9
    - supported_ratio < 0.5: confidence *= 0.8
    """
    if verification.total_facts == 0:
        return

    ratio = verification.supported_ratio
    if ratio >= 0.8:
        return

    try:
        content = concept_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return

    fm = fm_match.group(1)
    conf_match = re.search(r"^confidence:\s*([\d.]+)", fm, re.MULTILINE)
    if not conf_match:
        return

    current = float(conf_match.group(1))
    penalty = 0.8 if ratio < 0.5 else 0.9
    new_conf = round(max(0.1, current * penalty), 2)

    if new_conf == current:
        return

    new_fm = fm[:conf_match.start(1)] + str(new_conf) + fm[conf_match.end(1):]
    new_content = content[:fm_match.start(1)] + new_fm + content[fm_match.end(1):]

    fd, tmp_path = tempfile.mkstemp(dir=str(concept_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_content)
        os.replace(tmp_path, str(concept_path))
    except OSError:
        # Called per-concept inside verify --fix's batch loop (no outer
        # try/except) — unlike the sibling atomic-write helpers elsewhere,
        # re-raising here would abort the whole batch after one bad file.
        # Narrowed from bare Exception so a real bug in the surrounding
        # code wouldn't get silently absorbed here instead.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── Main entry point ──


def compute_fidelity_score(report: VerifyReport) -> int:
    """Compute 0-100 fidelity score.

    Formula: 100 * (supported + 0.5 * unverifiable) / total
    """
    total = report.total_facts
    if total == 0:
        return 100
    score = (report.supported + 0.5 * report.unverifiable) / total
    return max(0, min(100, round(score * 100)))


async def verify_knowledge_base(
    notes_dir: Path,
    provider: LLMProvider | None,
    language: Language = Language.EN,
    concept_names: list[str] | None = None,
    depth: str = "standard",
    force: bool = False,
    fix: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
) -> VerifyReport:
    """Main entry point: verify all or specified concepts."""
    from datetime import date

    from neocortex.config import get_data_dir

    concepts_dir = notes_dir / "concepts"
    report = VerifyReport(depth=depth, date=date.today().isoformat())

    if not concepts_dir.exists():
        return report

    # Cache: skip unchanged concepts
    cache = VerifyCache(get_data_dir() / "verify_cache.json")

    # Collect concept files to verify
    if concept_names:
        concept_files = []
        for name in concept_names:
            slug = name.strip().lower().replace(" ", "-")
            path = concepts_dir / f"{slug}.md"
            if path.exists():
                concept_files.append(path)
    else:
        concept_files = sorted(concepts_dir.glob("*.md"))

    if not concept_files:
        return report

    # Filter by cache (unless forced or specific concepts requested)
    if not force and not concept_names:
        concept_files = [cp for cp in concept_files if cache.needs_verify(cp)]
        if not concept_files:
            return report

    # Collect all note files (source material)
    note_files = [
        f for f in notes_dir.rglob("*.md")
        if "concepts" not in f.parts
        and "insights" not in f.parts
        and f.name != "INDEX.md"
        and f.name != "overview.md"
        and "diagrams" not in f.parts
        and "_reports" not in f.parts
        and ".flashcards" not in f.parts
    ]
    all_notes: dict[str, str] = {}
    for nf in note_files:
        try:
            all_notes[nf.name] = nf.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            pass

    total = len(concept_files)

    # Verify each concept
    for idx, concept_path in enumerate(concept_files):
        if on_progress:
            on_progress(idx + 1, total)

        try:
            concept_content = concept_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        entry = _load_concept_meta(concept_path)
        if entry is None:
            continue

        # Collect source note contents for this concept
        source_contents: dict[str, str] = {}
        for sn in entry.source_notes:
            if sn in all_notes:
                source_contents[sn] = all_notes[sn]

        # If concept has no recorded source notes, search all notes
        if not source_contents:
            source_contents = all_notes

        verification = await verify_concept(
            entry, concept_content, source_contents,
            provider, language, depth,
        )
        report.concept_results.append(verification)

        # Update cache
        cache.mark_verified(concept_path)

        # Confidence linkage (--fix mode)
        if fix:
            update_concept_confidence(concept_path, verification)

    # Deep mode: overview + claims cross-verification + self-consistency
    if depth == "deep" and provider is not None:
        # Overview verification
        overview_path = notes_dir / "overview.md"
        if overview_path.exists():
            try:
                overview_content = overview_path.read_text(encoding="utf-8")
                all_concept_names = [cp.stem for cp in concept_files]
                report.overview_checks = await verify_overview(
                    overview_content, all_concept_names, provider, language,
                )
            except (OSError, UnicodeDecodeError):
                pass

        # Claims cross-verification
        from neocortex.config import load_claims
        from neocortex.scanner.profile import normalize_gap_name

        all_claims = load_claims()
        for cv in report.concept_results:
            normalized = normalize_gap_name(cv.concept_name)
            concept_claims = all_claims.get(normalized, [])
            if not concept_claims:
                continue
            # Find concept body
            slug = cv.concept_name.strip().lower().replace(" ", "-")
            concept_path = concepts_dir / f"{slug}.md"
            if not concept_path.exists():
                continue
            try:
                body = extract_concept_body(concept_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            checks = await cross_verify_claims(
                cv.concept_name, body, concept_claims, provider, language,
            )
            report.claims_checks.extend(checks)

        # Self-consistency check on low-confidence concepts
        low_conf = [
            cv for cv in report.concept_results
            if cv.total_facts > 0 and cv.supported_ratio < 0.8
        ]
        for cv in low_conf[:5]:  # Limit to 5 concepts to control cost
            slug = cv.concept_name.strip().lower().replace(" ", "-")
            concept_path = concepts_dir / f"{slug}.md"
            if not concept_path.exists():
                continue
            try:
                body = extract_concept_body(concept_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            checks = await self_consistency_check(
                body, cv.concept_name, provider, language,
            )
            report.consistency_checks.extend(checks)

    # Aggregate totals
    for cv in report.concept_results:
        report.supported += cv.supported_count
        report.unsupported += cv.unsupported_count
        report.unverifiable += cv.unverifiable_count

    for check_list in (report.overview_checks, report.claims_checks, report.consistency_checks):
        for oc in check_list:
            if oc.verdict == FactVerdict.SUPPORTED:
                report.supported += 1
            elif oc.verdict == FactVerdict.UNSUPPORTED:
                report.unsupported += 1
            else:
                report.unverifiable += 1

    report.total_facts = report.supported + report.unsupported + report.unverifiable
    report.concepts_verified = len(report.concept_results)
    report.fidelity_score = compute_fidelity_score(report)

    # Persist cache
    cache.save()

    return report
