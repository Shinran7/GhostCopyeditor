"""Correspondence tests for shared per-hit TypeSafe budget."""

from __future__ import annotations

from ghostcopyeditor.typesafe.per_hit_budget import (
    PER_HIT_TYPESAFE_BUDGET,
    PerHitAskBudget,
)


def test_default_ceiling_is_twelve() -> None:
    assert PER_HIT_TYPESAFE_BUDGET == 12
    budget = PerHitAskBudget()
    assert budget.remaining == 12


def test_try_consume_tracks_used() -> None:
    budget = PerHitAskBudget(remaining=2)
    assert budget.try_consume() is True
    assert budget.try_consume() is True
    assert budget.try_consume() is False
    assert budget.used == 2
    assert budget.remaining == 0
