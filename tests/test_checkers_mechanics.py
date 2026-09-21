"""Design PR3 path for mechanics checker tests.

Canonical cases live under ``tests/ghostcopyeditor/checkers/``.
"""

from __future__ import annotations

from pathlib import Path


def test_design_mechanics_suite_present() -> None:
    root = Path(__file__).parent / "ghostcopyeditor" / "checkers"
    assert (root / "test_mechanics.py").is_file()
