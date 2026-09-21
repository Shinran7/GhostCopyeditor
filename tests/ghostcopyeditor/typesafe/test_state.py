"""State module correspondence test; full cases in test_suite.py."""

from __future__ import annotations

from ghostcopyeditor.typesafe import state


def test_state_exports() -> None:
    assert callable(state.truncate_middle)
    assert callable(state.build_typesafe_state)
    assert state.PROSE_MAX_CHARS == 12_000
