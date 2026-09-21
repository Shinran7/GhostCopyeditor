"""Design PR3 path for wordiness checker tests.

Canonical cases live under ``tests/ghostcopyeditor/checkers/``.
"""

from __future__ import annotations

from pathlib import Path


def test_design_wordiness_suite_present() -> None:
    root = Path(__file__).parent / "ghostcopyeditor" / "checkers"
    assert (root / "test_wordiness.py").is_file()
