"""Design PR2 path for ingest tests.

Canonical cases live under ``tests/ghostcopyeditor/ingestion/`` and
``tests/ghostcopyeditor/commands/`` (forward-coverage mirror).
"""

from __future__ import annotations

from pathlib import Path


def test_design_ingest_suite_present() -> None:
    root = Path(__file__).parent / "ghostcopyeditor"
    assert (root / "ingestion" / "test_markdown_loader.py").is_file()
    assert (root / "ingestion" / "test_discovery.py").is_file()
    assert (root / "commands" / "test_companion.py").is_file()
    assert (root / "commands" / "test_analyze.py").is_file()
