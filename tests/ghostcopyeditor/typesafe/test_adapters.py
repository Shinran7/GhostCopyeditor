"""Adapters module correspondence test; full cases in test_suite.py."""

from __future__ import annotations

from ghostcopyeditor.typesafe import adapters


def test_adapters_exports() -> None:
    assert callable(adapters.response_to_findings)
