"""Design PR3 path for checker registry tests.

Canonical cases live under ``tests/ghostcopyeditor/checkers/``.
"""

from __future__ import annotations

from pathlib import Path


def test_design_registry_suite_present() -> None:
    root = Path(__file__).parent / "ghostcopyeditor" / "checkers"
    assert (root / "test___init__.py").is_file()
