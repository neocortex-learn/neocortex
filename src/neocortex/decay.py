"""Knowledge confidence decay — implements Hidalgo's ~50% annual decay rate."""

from __future__ import annotations

from datetime import date

MONTHLY_DECAY_RATE = 0.056
DECAY_THRESHOLD = 0.3
REVIEW_BOOST = 0.05
NOTE_BOOST = 0.1
MAX_CONFIDENCE = 1.0


def months_between(date_a: str, date_b: str) -> float:
    """Return the number of months (possibly fractional) between two ISO dates.

    If *date_a* is empty or unparseable the result is ``0``.
    """
    if not date_a:
        return 0.0
    try:
        a = date.fromisoformat(date_a)
        b = date.fromisoformat(date_b)
    except (ValueError, TypeError):
        return 0.0
    delta_days = (b - a).days
    return delta_days / 30.44


def decayed_confidence(confidence: float, last_updated: str) -> float:
    """Return *confidence* after time-decay from *last_updated* until today."""
    today = date.today().isoformat()
    months = months_between(last_updated, today)
    if months <= 0:
        return confidence
    return max(0.0, confidence * (1 - MONTHLY_DECAY_RATE) ** months)


def boost_confidence(current: float, amount: float) -> float:
    """Increase *current* by *amount*, capped at :data:`MAX_CONFIDENCE`."""
    return min(MAX_CONFIDENCE, current + amount)


def knowledge_complexity(concepts: list) -> dict:
    """Compute a knowledge-complexity score from a list of :class:`ConceptEntry`.

    Complexity = concept_count * avg_depth * connectivity.

    Returns a dict with keys ``score``, ``concept_count``, ``avg_depth``,
    ``connectivity``, and ``decaying`` (names below threshold).
    """
    if not concepts:
        return {
            "score": 0.0,
            "concept_count": 0,
            "avg_depth": 0.0,
            "connectivity": 0.0,
            "decaying": [],
        }

    concept_count = len(concepts)

    depths: list[float] = []
    decaying: list[str] = []
    concept_names = {c.name for c in concepts}
    edge_count = 0

    for c in concepts:
        d = decayed_confidence(c.confidence, c.last_updated)
        depths.append(d)
        if d < DECAY_THRESHOLD:
            decaying.append(c.name)
        for rel in c.related_concepts:
            if rel in concept_names:
                edge_count += 1

    edge_count //= 2
    avg_depth = sum(depths) / concept_count
    max_edges = concept_count * (concept_count - 1) / 2 if concept_count > 1 else 1
    connectivity = edge_count / max_edges

    score = concept_count * avg_depth * connectivity

    return {
        "score": score,
        "concept_count": concept_count,
        "avg_depth": round(avg_depth, 4),
        "connectivity": round(connectivity, 4),
        "decaying": decaying,
    }
