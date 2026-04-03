"""SM-2 spaced repetition scheduler."""

from __future__ import annotations

from datetime import date, timedelta

from neocortex.models import Flashcard


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


def get_review_session(cards: list[Flashcard], max_cards: int = 20) -> list[Flashcard]:
    """Select due cards for today's session, sorted by priority."""
    today = date.today().isoformat()
    due = [c for c in cards if not c.next_review or c.next_review <= today]

    def _sort_key(c: Flashcard) -> tuple[int, str]:
        if c.last_review:
            return (0, c.next_review or "")
        return (1, c.next_review or "")

    due.sort(key=_sort_key)
    return due[:max_cards]
