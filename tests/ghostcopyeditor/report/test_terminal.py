"""Colocated coverage for report.terminal (canonical cases in tests/test_report.py)."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from ghostcopyeditor.models.report import CopyEditReport, ReportSummary
from ghostcopyeditor.report.terminal import render_report


def test_render_empty_findings() -> None:
    report = CopyEditReport(
        ghostcopyeditor_version="0.1.0",
        mode="companion",
        generated_at="2026-09-21T16:00:00+00:00",
        manuscript_path="/chapter-001.md",
        manuscript_name="story · Chapter 1",
        story_slug="story",
        chapter_number=1,
        summary=ReportSummary(chapters_scanned=1),
    )
    buf = StringIO()
    render_report(
        report,
        console=Console(file=buf, force_terminal=False, width=80, color_system=None),
    )
    assert "No findings" in buf.getvalue()
