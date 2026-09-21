"""Judgments module correspondence test; full cases in test_suite.py."""

from __future__ import annotations

from ghostcopyeditor.typesafe import judgments


def test_judgments_exports() -> None:
    assert callable(judgments.run_typesafe_judgments)
