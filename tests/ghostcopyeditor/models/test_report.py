"""Tests for CopyEditReport skeleton (finding_ids only on chapters)."""

from __future__ import annotations

from pathlib import Path

from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Location,
    Severity,
)
from ghostcopyeditor.models.report import ChapterResult, CopyEditReport, ReportSummary


def _chapter(text: str, *, num: int = 18) -> Chapter:
    return Chapter(
        title=f"Chapter {num}",
        content=text,
        chapter_number=num,
        source_path=Path(f"/story/chapters/chapter-{num:03d}.md"),
    )


class TestReportSkeleton:
    def test_chapter_result_has_finding_ids_only(self) -> None:
        result = ChapterResult(
            chapter_number=18,
            chapter_path="chapter-018.md",
            title="Chapter 18",
            finding_ids=["det-c018-0001"],
        )
        data = result.to_dict()
        assert data["finding_ids"] == ["det-c018-0001"]
        assert "findings" not in data

    def test_empty_report_wires_chapters(self) -> None:
        ch = _chapter("# Chapter 18\n\nHi.\n", num=18)
        report = CopyEditReport.empty(
            mode="companion",
            manuscript_path=str(ch.source_path),
            manuscript_name="story · Chapter 18",
            story_slug="story",
            chapter_number=18,
            chapters=[ch],
            typesafe_enabled=False,
            llm_enabled=False,
            apply=False,
            findings=[],
        )
        data = report.to_dict()
        assert data["findings"] == []
        assert data["chapters"][0]["finding_ids"] == []
        assert data["summary"]["chapters_scanned"] == 1
        assert data["summary"]["total_findings"] == 0
        assert "findings" not in data["chapters"][0]

    def test_report_summary_from_findings(self) -> None:
        loc = Location(chapter_number=1, chapter_path="c.md")
        findings = [
            Finding(
                id="det-c001-0001",
                category=Category.GRAMMAR,
                severity=Severity.ERROR,
                message="x",
                location=loc,
                engine=Engine.DETERMINISTIC,
                metadata={"applied": True},
            ),
            Finding(
                id="llm-c001-0001",
                category=Category.GARBLED,
                severity=Severity.WARNING,
                message="y",
                location=loc,
                engine=Engine.LLM,
            ),
        ]
        summary = ReportSummary.from_findings(findings, chapters_scanned=1)
        assert summary.total_findings == 2
        assert summary.by_severity["error"] == 1
        assert summary.by_severity["warning"] == 1
        assert summary.by_category["grammar"] == 1
        assert summary.by_engine["deterministic"] == 1
        assert summary.by_engine["llm"] == 1
        assert summary.applied_count == 1

    def test_report_maps_finding_ids_per_chapter(self) -> None:
        ch1 = _chapter("# One\n", num=1)
        ch2 = _chapter("# Two\n", num=2)
        findings = [
            Finding(
                id="det-c001-0001",
                category=Category.GRAMMAR,
                severity=Severity.ERROR,
                message="a",
                location=Location(chapter_number=1, chapter_path="1.md"),
                engine=Engine.DETERMINISTIC,
            ),
            Finding(
                id="det-c002-0001",
                category=Category.GRAMMAR,
                severity=Severity.ERROR,
                message="b",
                location=Location(chapter_number=2, chapter_path="2.md"),
                engine=Engine.DETERMINISTIC,
            ),
        ]
        report = CopyEditReport.empty(
            mode="analyze",
            manuscript_path="/story/chapters",
            manuscript_name="story",
            story_slug="story",
            chapter_number=None,
            chapters=[ch1, ch2],
            typesafe_enabled=False,
            llm_enabled=False,
            apply=False,
            findings=findings,
        )
        data = report.to_dict()
        assert data["chapters"][0]["finding_ids"] == ["det-c001-0001"]
        assert data["chapters"][1]["finding_ids"] == ["det-c002-0001"]
        assert len(data["findings"]) == 2
