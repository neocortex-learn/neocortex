"""SM-2 spaced repetition scheduler."""

from __future__ import annotations

from datetime import date, timedelta

from neocortex.models import Flashcard


def is_active(card: Flashcard) -> bool:
    """Suspended (软淘汰) cards are excluded from every queue and count."""
    return not card.suspended


def is_due(card: Flashcard, today: str | None = None) -> bool:
    """The ONE due predicate. daily count / session queue / CLI 都必须走这里，
    不允许在别处复制 `next_review <= today` 逻辑。"""
    if today is None:
        today = date.today().isoformat()
    return not card.next_review or card.next_review <= today


def sm2_update(card: Flashcard, quality: int) -> Flashcard:
    """Update flashcard SM-2 parameters based on user rating (0-5)."""
    quality = max(0, min(5, quality))
    today = date.today()

    if quality >= 3:
        if card.review_count == 0:
            new_interval = 1
        elif card.review_count == 1:
            new_interval = 6
        else:
            new_interval = round(card.interval * card.ease_factor)
        new_ef = card.ease_factor + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
        new_ef = max(1.3, new_ef)
        card.interval = new_interval
        card.ease_factor = round(new_ef, 2)
        card.review_count += 1
    else:
        card.interval = 1
        card.review_count = 0

    card.next_review = (today + timedelta(days=card.interval)).isoformat()
    card.last_review = today.isoformat()
    return card


def get_review_session(
    cards: list[Flashcard],
    max_cards: int = 20,
    mode: str = "default",
    today: str | None = None,
) -> list[Flashcard]:
    """Select cards for review session.

    Modes:
    - default: due cards, interleaved across concepts/sources
    - diagnostic: random sample across ALL cards (not just due), test coverage
    - drill: only struggling cards (ease_factor < 2.0), ignore schedule
    - hard: due cards with ease_factor < 2.3 first, then others
    """
    cards = [c for c in cards if is_active(c)]

    if mode == "diagnostic":
        return _diagnostic_session(cards, max_cards)
    if mode == "drill":
        return _drill_session(cards, max_cards)
    if mode == "hard":
        return _hard_session(cards, max_cards, today=today)

    # Default: due cards, interleaved
    due = [c for c in cards if is_due(c, today)]

    def _sort_key(c: Flashcard) -> tuple[int, str]:
        if c.last_review:
            return (0, c.next_review or "")
        return (1, c.next_review or "")

    due.sort(key=_sort_key)
    due = due[:max_cards]
    return _interleave(due)


def _diagnostic_session(cards: list[Flashcard], max_cards: int) -> list[Flashcard]:
    """Random sample across all cards, not just due. Tests coverage breadth."""
    import random
    pool = list(cards)
    random.shuffle(pool)
    return pool[:max_cards]


def _drill_session(cards: list[Flashcard], max_cards: int) -> list[Flashcard]:
    """Only struggling cards (ease_factor < 2.0), regardless of schedule."""
    struggling = [c for c in cards if c.ease_factor < 2.0]
    struggling.sort(key=lambda c: c.ease_factor)
    return struggling[:max_cards]


def _hard_session(
    cards: list[Flashcard], max_cards: int, today: str | None = None,
) -> list[Flashcard]:
    """Due cards, but hard ones (ease_factor < 2.3) first."""
    due = [c for c in cards if is_due(c, today)]
    hard = [c for c in due if c.ease_factor < 2.3]
    normal = [c for c in due if c.ease_factor >= 2.3]
    combined = hard + normal
    return _interleave(combined[:max_cards])


def _interleave(cards: list[Flashcard]) -> list[Flashcard]:
    """Interleave cards across different sources/concepts to avoid blocking.

    Based on Tulving's research: interleaving topics improves retention
    compared to reviewing all cards from the same source consecutively.
    """
    if len(cards) <= 2:
        return cards

    # Group by source note (or concept for relationship cards)
    groups: dict[str, list[Flashcard]] = {}
    for c in cards:
        key = c.source_note or c.concept or "unknown"
        groups.setdefault(key, []).append(c)

    # Round-robin across groups
    result: list[Flashcard] = []
    group_lists = list(groups.values())
    idx = 0
    while len(result) < len(cards):
        added = False
        for g in group_lists:
            if idx < len(g):
                result.append(g[idx])
                added = True
        if not added:
            break
        idx += 1

    return result
