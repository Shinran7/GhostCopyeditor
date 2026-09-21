"""Project coverage gate: 85% branch coverage.

coverage.py's fail_under number mixes lines and branches. This gate uses
branch coverage only.
"""

from __future__ import annotations

from typing import Any

BRANCH_COVERAGE_MIN = 85.0


def branch_percent(cov: Any) -> float | None:
    """Return branch coverage for *cov*, or None when branches were not measured."""
    data = cov.get_data()
    if not data.has_arcs():
        return None
    total = None
    for filename in data.measured_files():
        numbers = cov._analyze(filename).numbers
        total = numbers if total is None else total + numbers
    if total is None or total.n_branches == 0:
        return None
    return float(total.pc_branches)


def branch_coverage_failed(
    percent: float | None, minimum: float = BRANCH_COVERAGE_MIN
) -> bool:
    """True when branch coverage is missing or under the required percent."""
    return percent is None or percent < minimum
