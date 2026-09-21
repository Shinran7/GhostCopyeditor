"""Design PR3 path for style checker tests.

Canonical cases live under ``tests/ghostcopyeditor/checkers/``.
"""

from __future__ import annotations

from pathlib import Path


def test_design_style_suite_present() -> None:
    root = Path(__file__).parent / "ghostcopyeditor" / "checkers"
    assert (root / "test_style.py").is_file()
