"""Design PR4 path for TypeSafe tests.

Canonical cases live under ``tests/ghostcopyeditor/typesafe/``.
"""

from __future__ import annotations

from pathlib import Path


def test_design_typesafe_suite_present() -> None:
    root = Path(__file__).parent / "ghostcopyeditor" / "typesafe"
    assert (root / "test_client.py").is_file()
    assert (root / "test_adapters.py").is_file()
    assert (root / "test_suite.py").is_file()
