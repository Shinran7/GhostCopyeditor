"""Design path pointer for earth anachronism fixtures."""

from __future__ import annotations

from pathlib import Path


def test_earth_anachronism_suite_present() -> None:
    root = Path(__file__).parent / "ghostcopyeditor" / "checkers"
    assert (root / "test_anachronism.py").is_file()
