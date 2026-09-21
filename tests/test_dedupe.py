"""Design PR3 path for dedupe / pipeline tests.

Canonical cases live under ``tests/ghostcopyeditor/pipeline/``.
"""

from __future__ import annotations

from pathlib import Path


def test_design_dedupe_suite_present() -> None:
    root = Path(__file__).parent / "ghostcopyeditor" / "pipeline"
    assert (root / "test_runner.py").is_file()
