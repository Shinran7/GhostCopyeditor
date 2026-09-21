"""Design PR2 path for Finding model tests.

Canonical cases live under ``tests/ghostcopyeditor/models/``
(forward-coverage mirror).
"""

from __future__ import annotations

from pathlib import Path


def test_design_finding_suite_present() -> None:
    root = Path(__file__).parent / "ghostcopyeditor" / "models"
    assert (root / "test_finding.py").is_file()
    assert (root / "test_report.py").is_file()
