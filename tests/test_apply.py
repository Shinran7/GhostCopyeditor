"""Design PR3 path for --apply tests.

Canonical cases live under ``tests/ghostcopyeditor/checkers/``.
"""

from __future__ import annotations

from pathlib import Path


def test_design_apply_suite_present() -> None:
    root = Path(__file__).parent / "ghostcopyeditor" / "checkers"
    assert (root / "test_apply.py").is_file()
