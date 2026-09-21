"""Package export smoke for pipeline."""

from __future__ import annotations

from ghostcopyeditor.pipeline import (
    dedupe_findings,
    run_analyze_pipeline,
    run_chapter_pipeline,
)


def test_pipeline_exports() -> None:
    assert callable(dedupe_findings)
    assert callable(run_chapter_pipeline)
    assert callable(run_analyze_pipeline)
