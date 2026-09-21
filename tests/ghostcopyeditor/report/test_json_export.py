"""Colocated coverage for report.json_export (canonical cases in tests/test_report.py)."""

from __future__ import annotations

import json
from pathlib import Path

from ghostcopyeditor.models.report import CopyEditReport, ReportSummary
from ghostcopyeditor.report.json_export import (
    REQUIRED_TOP_LEVEL_KEYS,
    persist_report_json,
    report_to_payload,
    validate_autonomicon_schema,
)


def test_empty_report_payload_has_required_keys(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text("format: json\n", encoding="utf-8")
    chapter = tmp_path / "chapter-001.md"
    chapter.write_text("# One\n", encoding="utf-8")
    report = CopyEditReport(
        ghostcopyeditor_version="0.1.0",
        mode="companion",
        generated_at="2026-09-21T16:00:00+00:00",
        manuscript_path=str(chapter),
        manuscript_name="tmp · Chapter 1",
        story_slug="tmp",
        chapter_number=1,
        summary=ReportSummary(chapters_scanned=1),
    )
    payload = report_to_payload(report)
    assert REQUIRED_TOP_LEVEL_KEYS <= set(payload)
    assert validate_autonomicon_schema(payload) == []
    path = persist_report_json(report, project_root=tmp_path, manuscript_path=chapter)
    assert path.name == "companion-ch001.json"
    assert json.loads(path.read_text(encoding="utf-8"))["mode"] == "companion"


def test_autonomicon_story_report_stays_in_story_reports(tmp_path: Path) -> None:
    story = tmp_path / "stories" / "shatterbound"
    chapter = story / "chapters" / "chapter-001.md"
    chapter.parent.mkdir(parents=True)
    chapter.write_text("# One\n", encoding="utf-8")
    report = CopyEditReport(
        ghostcopyeditor_version="0.1.0",
        mode="companion",
        generated_at="2026-09-21T16:00:00+00:00",
        manuscript_path=str(chapter),
        manuscript_name="shatterbound · Chapter 1",
        story_slug="shatterbound",
        chapter_number=1,
        summary=ReportSummary(chapters_scanned=1),
    )
    path = persist_report_json(report, manuscript_path=chapter)
    assert path == story / "reports" / "ghostcopyeditor-companion-ch001.json"
    assert not (story / ".ghostcopyeditor").exists()
