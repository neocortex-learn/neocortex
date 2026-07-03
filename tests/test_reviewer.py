"""Tests for SM-2 spaced repetition — scheduling, flashcard storage, due cards."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from neocortex.models import Flashcard
from neocortex.reviewer import get_review_session, sm2_update


# ── Helpers ──


def _card(
    card_id: str = "abc",
    next_review: str = "",
    interval: int = 1,
    ease_factor: float = 2.5,
    review_count: int = 0,
    last_review: str | None = None,
    **kwargs,
) -> Flashcard:
    return Flashcard(
        id=card_id,
        source_note="test-note.md",
        question="What is X?",
        answer="X is Y.",
        next_review=next_review,
        interval=interval,
        ease_factor=ease_factor,
        review_count=review_count,
        last_review=last_review,
        **kwargs,
    )


# ── SM-2 algorithm ──


class TestSm2Update:
    def test_first_pass_sets_interval_1(self):
        card = _card(review_count=0)
        updated = sm2_update(card, quality=4)
        assert updated.interval == 1
        assert updated.review_count == 1
        assert updated.next_review == (date.today() + timedelta(days=1)).isoformat()

    def test_second_pass_sets_interval_6(self):
        card = _card(review_count=1, interval=1)
        updated = sm2_update(card, quality=4)
        assert updated.interval == 6
        assert updated.review_count == 2

    def test_third_pass_uses_ease_factor(self):
        card = _card(review_count=2, interval=6, ease_factor=2.5)
        updated = sm2_update(card, quality=4)
        assert updated.interval == 15  # round(6 * 2.5)
        assert updated.review_count == 3

    def test_quality_5_increases_ease(self):
        card = _card(review_count=2, interval=6, ease_factor=2.5)
        updated = sm2_update(card, quality=5)
        assert updated.ease_factor == 2.6

    def test_quality_3_barely_passes(self):
        card = _card(review_count=2, interval=6, ease_factor=2.5)
        updated = sm2_update(card, quality=3)
        assert updated.ease_factor == 2.36
        assert updated.review_count == 3

    def test_fail_resets_interval_and_count(self):
        card = _card(review_count=5, interval=30, ease_factor=2.1)
        updated = sm2_update(card, quality=2)
        assert updated.interval == 1
        assert updated.review_count == 0
        assert updated.ease_factor == 2.1  # preserved

    def test_fail_quality_0(self):
        card = _card(review_count=3, interval=15, ease_factor=2.5)
        updated = sm2_update(card, quality=0)
        assert updated.interval == 1
        assert updated.review_count == 0

    def test_fail_quality_1(self):
        card = _card(review_count=2, interval=10, ease_factor=2.3)
        updated = sm2_update(card, quality=1)
        assert updated.interval == 1
        assert updated.review_count == 0
        assert updated.ease_factor == 2.3

    def test_ease_factor_floor_at_1_3(self):
        card = _card(review_count=2, interval=6, ease_factor=1.3)
        updated = sm2_update(card, quality=3)
        assert updated.ease_factor == 1.3

    def test_last_review_set_to_today(self):
        card = _card()
        updated = sm2_update(card, quality=4)
        assert updated.last_review == date.today().isoformat()

    def test_next_review_calculated_correctly(self):
        card = _card(review_count=1, interval=1)
        updated = sm2_update(card, quality=4)
        expected = (date.today() + timedelta(days=6)).isoformat()
        assert updated.next_review == expected

    def test_quality_clamped_to_0_5(self):
        card = _card()
        updated = sm2_update(card, quality=10)
        assert updated.review_count == 1  # treated as 5

        card2 = _card()
        updated2 = sm2_update(card2, quality=-3)
        assert updated2.review_count == 0  # treated as 0, fail


# ── Review session selection ──


class TestGetReviewSession:
    def test_selects_due_cards(self):
        today = date.today().isoformat()
        c1 = _card(card_id="1", next_review=today)
        c2 = _card(card_id="2", next_review=(date.today() + timedelta(days=5)).isoformat())
        result = get_review_session([c1, c2])
        assert len(result) == 1
        assert result[0].id == "1"

    def test_includes_overdue_cards(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        c = _card(card_id="1", next_review=yesterday, last_review="2026-01-01")
        result = get_review_session([c])
        assert len(result) == 1

    def test_includes_cards_with_empty_next_review(self):
        c = _card(card_id="1", next_review="")
        result = get_review_session([c])
        assert len(result) == 1

    def test_overdue_before_new(self):
        overdue = _card(card_id="old", next_review="2026-01-01", last_review="2025-12-25")
        new_card = _card(card_id="new", next_review="")
        result = get_review_session([new_card, overdue])
        assert result[0].id == "old"
        assert result[1].id == "new"

    def test_respects_max_cards(self):
        cards = [_card(card_id=str(i), next_review=date.today().isoformat()) for i in range(50)]
        result = get_review_session(cards, max_cards=10)
        assert len(result) == 10

    def test_empty_list(self):
        assert get_review_session([]) == []

    def test_no_due_cards(self):
        future = (date.today() + timedelta(days=30)).isoformat()
        c = _card(card_id="1", next_review=future)
        result = get_review_session([c])
        assert result == []


# ── Flashcard storage (config.py functions) ──


@pytest.fixture()
def notes_dir(tmp_path):
    return tmp_path


class TestFlashcardStorage:
    def test_save_and_load_roundtrip(self, notes_dir):
        from neocortex.config import load_flashcards, save_flashcards

        cards = [
            Flashcard(
                id="a1",
                source_note="test-note.md",
                question="Q1?",
                answer="A1.",
                next_review="2026-04-01",
            ),
            Flashcard(
                id="a2",
                source_note="test-note.md",
                question="Q2?",
                answer="A2.",
                concept="testing",
                difficulty="hard",
                next_review="2026-04-02",
            ),
        ]
        save_flashcards(notes_dir, "test-note", cards)
        loaded = load_flashcards(notes_dir)
        assert len(loaded) == 2
        assert loaded[0].id == "a1"
        assert loaded[1].concept == "testing"
        assert loaded[1].difficulty == "hard"

    def test_load_empty_dir(self, notes_dir):
        from neocortex.config import load_flashcards

        assert load_flashcards(notes_dir) == []

    def test_load_no_flashcards_dir(self, notes_dir):
        from neocortex.config import load_flashcards

        assert load_flashcards(notes_dir) == []

    def test_load_skips_corrupt_json(self, notes_dir):
        from neocortex.config import load_flashcards

        fc_dir = notes_dir / ".flashcards"
        fc_dir.mkdir()
        (fc_dir / "bad.json").write_text("not json", encoding="utf-8")
        assert load_flashcards(notes_dir) == []

    def test_save_creates_flashcards_dir(self, notes_dir):
        from neocortex.config import save_flashcards

        card = Flashcard(id="x", source_note="n.md", question="Q?", answer="A.")
        save_flashcards(notes_dir, "n", [card])
        assert (notes_dir / ".flashcards").exists()
        assert (notes_dir / ".flashcards" / "n.json").exists()

    def test_save_overwrites_existing(self, notes_dir):
        from neocortex.config import load_flashcards, save_flashcards

        c1 = Flashcard(id="1", source_note="n.md", question="Q1?", answer="A1.")
        save_flashcards(notes_dir, "n", [c1])

        c2 = Flashcard(id="2", source_note="n.md", question="Q2?", answer="A2.")
        save_flashcards(notes_dir, "n", [c2])

        loaded = load_flashcards(notes_dir)
        assert len(loaded) == 1
        assert loaded[0].id == "2"

    def test_multiple_note_files(self, notes_dir):
        from neocortex.config import load_flashcards, save_flashcards

        c1 = Flashcard(id="1", source_note="note-a.md", question="Q1?", answer="A1.")
        c2 = Flashcard(id="2", source_note="note-b.md", question="Q2?", answer="A2.")
        save_flashcards(notes_dir, "note-a", [c1])
        save_flashcards(notes_dir, "note-b", [c2])

        loaded = load_flashcards(notes_dir)
        assert len(loaded) == 2
        ids = {c.id for c in loaded}
        assert ids == {"1", "2"}

    def test_atomic_write(self, notes_dir):
        from neocortex.config import save_flashcards

        card = Flashcard(id="x", source_note="n.md", question="Q?", answer="A.")
        save_flashcards(notes_dir, "n", [card])

        fc_dir = notes_dir / ".flashcards"
        tmp_files = list(fc_dir.glob("*.tmp"))
        assert tmp_files == []


# ── Due flashcard filtering ──


class TestGetDueFlashcards:
    def test_returns_due_today(self, notes_dir):
        from neocortex.config import get_due_flashcards, save_flashcards

        today = date.today().isoformat()
        c = Flashcard(id="1", source_note="n.md", question="Q?", answer="A.", next_review=today)
        save_flashcards(notes_dir, "n", [c])

        due = get_due_flashcards(notes_dir)
        assert len(due) == 1

    def test_returns_overdue(self, notes_dir):
        from neocortex.config import get_due_flashcards, save_flashcards

        past = (date.today() - timedelta(days=3)).isoformat()
        c = Flashcard(id="1", source_note="n.md", question="Q?", answer="A.", next_review=past)
        save_flashcards(notes_dir, "n", [c])

        due = get_due_flashcards(notes_dir)
        assert len(due) == 1

    def test_excludes_future(self, notes_dir):
        from neocortex.config import get_due_flashcards, save_flashcards

        future = (date.today() + timedelta(days=7)).isoformat()
        c = Flashcard(id="1", source_note="n.md", question="Q?", answer="A.", next_review=future)
        save_flashcards(notes_dir, "n", [c])

        due = get_due_flashcards(notes_dir)
        assert len(due) == 0

    def test_includes_empty_next_review(self, notes_dir):
        from neocortex.config import get_due_flashcards, save_flashcards

        c = Flashcard(id="1", source_note="n.md", question="Q?", answer="A.", next_review="")
        save_flashcards(notes_dir, "n", [c])

        due = get_due_flashcards(notes_dir)
        assert len(due) == 1

    def test_empty_dir(self, notes_dir):
        from neocortex.config import get_due_flashcards

        assert get_due_flashcards(notes_dir) == []
