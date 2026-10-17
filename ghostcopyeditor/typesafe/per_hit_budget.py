"""Shared per-hit TypeSafe ask budget (garbled + missing-predicate)."""

from __future__ import annotations

from dataclasses import dataclass, field

PER_HIT_TYPESAFE_BUDGET = 12


@dataclass
class PerHitAskBudget:
    """Mutable chapter ceiling for per-finding TypeSafe confirms."""

    remaining: int = PER_HIT_TYPESAFE_BUDGET
    used: int = field(default=0, init=False)

    def try_consume(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        self.used += 1
        return True


__all__ = ["PER_HIT_TYPESAFE_BUDGET", "PerHitAskBudget"]
