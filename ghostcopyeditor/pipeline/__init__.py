"""Copy-edit pipeline orchestration."""

from __future__ import annotations

from ghostcopyeditor.pipeline.runner import (
    dedupe_findings,
    run_analyze_pipeline,
    run_chapter_pipeline,
)

__all__ = [
    "dedupe_findings",
    "run_analyze_pipeline",
    "run_chapter_pipeline",
]
