"""Routing module correspondence test; full cases in test_suite.py."""

from __future__ import annotations

from ghostcopyeditor.typesafe import routing


def test_routing_exports() -> None:
    assert hasattr(routing, "resolve_typesafe_enabled")
    assert hasattr(routing, "noul_band")
    assert routing.NOUL_MID_BAND_LOW == 0.35
