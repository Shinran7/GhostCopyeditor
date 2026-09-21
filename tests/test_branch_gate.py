"""The branch-coverage gate fails under 85% and passes at or above it."""

from __future__ import annotations

from tests.branch_gate import branch_coverage_failed


def test_branch_gate_threshold() -> None:
    assert branch_coverage_failed(84.99) is True
    assert branch_coverage_failed(None) is True
    assert branch_coverage_failed(85.0) is False
    assert branch_coverage_failed(87.66) is False
