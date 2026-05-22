"""Concept map service — pure data version of ``kb map``.

The CLI command writes a file under ``maps/`` and offers to open it; this
service returns the Mermaid source so the GUI can render in-place via
MermaidView (no extra file produced). Filtering args mirror the CLI:
``domain`` narrows to a known domain, ``around`` to one concept's
neighbourhood.
"""

from __future__ import annotations

import re
from pathlib import Path

from neocortex.models import ConceptMap, Profile


def _concept_slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())


def _star_rating(evidence_count: int) -> str:
    if evidence_count >= 3:
        return "★★★"
    if evidence_count >= 1:
        return "★★☆"
    return "★☆☆"


def _node_style(slug: str, evidence_count: int) -> str:
    if evidence_count >= 3:
        return f"    style {slug} fill:#2d5016,color:#fff"
    if evidence_count >= 1:
        return f"    style {slug} fill:#8b6914,color:#fff"
    return f"    style {slug} fill:#555,color:#fff"


def build_concept_map(
    *,
    notes_dir: Path,
    profile: Profile,
    domain: str | None = None,
    around: str | None = None,
) -> ConceptMap:
    """Return a Mermaid ``graph LR`` source string with optional filtering.

    ``domain`` and ``around`` mirror the CLI flags. They are mutually
    exclusive in spirit but not enforced — if both are passed, domain runs
    first, then around within that subset.
    """
    from neocortex.compiler import collect_all_concepts, match_domain

    concepts_dir = notes_dir / "concepts"
    concepts = collect_all_concepts(concepts_dir)

    if not concepts:
        return ConceptMap(
            mermaid_source="graph LR\n    empty[\"没有已编译概念<br/>先跑 kb compile\"]",
            concepts_returned=0,
            edges_returned=0,
            filter_description="none",
        )

    known_domains = {d.lower() for d in profile.skills.domains}
    filter_desc = "none"

    if domain:
        concepts = [
            c for c in concepts
            if match_domain(c.name, known_domains) == domain.lower()
        ]
        filter_desc = f"domain={domain}"

    if around:
        around_lower = around.lower()
        center = next((c for c in concepts if c.name.lower() == around_lower), None)
        if center is None:
            return ConceptMap(
                mermaid_source=f'graph LR\n    none["没有找到 \\"{around}\\""]',
                concepts_returned=0,
                edges_returned=0,
                filter_description=f"around={around}",
            )
        neighbour_names = {n.lower() for n in center.related_concepts}
        neighbour_names.add(center.name.lower())
        concepts = [c for c in concepts if c.name.lower() in neighbour_names]
        filter_desc = f"around={around}"

    if not concepts:
        return ConceptMap(
            mermaid_source='graph LR\n    none["过滤后没有概念"]',
            concepts_returned=0,
            edges_returned=0,
            filter_description=filter_desc,
        )

    concept_map = {c.name: c for c in concepts}
    lines = ["graph LR"]
    styles: list[str] = []
    seen_edges: set[tuple[str, str]] = set()

    for c in concepts:
        slug = _concept_slug(c.name)
        display = f"{c.name} {_star_rating(c.evidence_count)}"
        safe = display.replace('"', "'")
        lines.append(f'    {slug}["{safe}"]')
        styles.append(_node_style(slug, c.evidence_count))

    for c in concepts:
        src_slug = _concept_slug(c.name)
        for rel in c.related_concepts:
            if rel in concept_map:
                dst_slug = _concept_slug(rel)
                key = tuple(sorted((src_slug, dst_slug)))
                if key not in seen_edges:
                    seen_edges.add(key)
                    lines.append(f"    {src_slug} --> {dst_slug}")

    lines.extend(styles)

    return ConceptMap(
        mermaid_source="\n".join(lines),
        concepts_returned=len(concepts),
        edges_returned=len(seen_edges),
        filter_description=filter_desc,
    )
