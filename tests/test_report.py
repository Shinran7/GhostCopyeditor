"""Terminal + JSON report emitters and Autonomicon golden schema."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Location,
    Severity,
)
from ghostcopyeditor.models.report import ChapterResult, CopyEditReport, ReportSummary
from ghostcopyeditor.report import (
    REQUIRED_TOP_LEVEL_KEYS,
    export_json,
    persist_report_json,
    render_report,
    report_persist_path,
    report_to_payload,
    validate_autonomicon_schema,
)
from ghostcopyeditor.report.json_export import REQUIRED_CHAPTER_KEYS, REQUIRED_SUMMARY_KEYS

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN_PATH = FIXTURES / "golden_companion_report.json"


def _load_golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _sample_report() -> CopyEditReport:
    loc = Location(
        chapter_number=18,
        chapter_path="C:/novels/the-jailer-s-wound/chapters/chapter-018.md",
        line_start=42,
        line_end=42,
        char_start=1024,
        char_end=1026,
        excerpt="He  walked",
    )
    findings = [
        Finding(
            id="det-c018-0001",
            category=Category.GRAMMAR,
            severity=Severity.ERROR,
            message="Double space between words.",
            suggestion="Use a single space.",
            engine=Engine.DETERMINISTIC,
            rule_id="mech.double_space",
            applyable=True,
            replacement=" ",
            location=loc,
            metadata={"expected_old": "  "},
        ),
        Finding(
            id="llm-c018-0001",
            category=Category.GARBLED,
            severity=Severity.WARNING,
            message="Possible mid-edit wreckage.",
            suggestion="Rewrite the sentence cleanly.",
            engine=Engine.LLM,
            rule_id="llm.garbled",
            applyable=False,
            confidence=0.82,
            location=Location(
                chapter_number=18,
                chapter_path=loc.chapter_path,
                line_start=50,
                line_end=50,
                char_start=1400,
                char_end=1430,
                excerpt="He the the walked toward",
            ),
        ),
        Finding(
            id="det-c018-0002",
            category=Category.WORDINESS,
            severity=Severity.SUGGESTION,
            message="Wordy phrase.",
            suggestion="Prefer a tighter wording.",
            engine=Engine.DETERMINISTIC,
            rule_id="word.in_order_to",
            applyable=True,
            replacement="to",
            location=Location(
                chapter_number=18,
                chapter_path=loc.chapter_path,
                line_start=60,
                line_end=60,
                char_start=1800,
                char_end=1811,
                excerpt="in order to",
            ),
            metadata={"expected_old": "in order to"},
        ),
    ]
    return CopyEditReport(
        ghostcopyeditor_version="0.1.0",
        mode="companion",
        generated_at="2026-09-21T16:00:00+00:00",
        manuscript_path=loc.chapter_path,
        manuscript_name="the-jailer-s-wound · Chapter 18",
        story_slug="the-jailer-s-wound",
        chapter_number=18,
        summary=ReportSummary.from_findings(findings, chapters_scanned=1),
        findings=findings,
        chapters=[
            ChapterResult(
                chapter_number=18,
                chapter_path=loc.chapter_path,
                title="Chapter 18",
                finding_ids=[f.id for f in findings],
            )
        ],
        warnings=[],
        typesafe_enabled=False,
        llm_enabled=True,
        apply=False,
    )


class TestGoldenSchema:
    def test_golden_fixture_passes_validator(self) -> None:
        payload = _load_golden()
        assert validate_autonomicon_schema(payload) == []

    def test_golden_required_keys_checklist(self) -> None:
        payload = _load_golden()
        assert REQUIRED_TOP_LEVEL_KEYS <= set(payload)
        assert REQUIRED_SUMMARY_KEYS <= set(payload["summary"])
        assert all(REQUIRED_CHAPTER_KEYS <= set(ch) for ch in payload["chapters"])
        assert all("findings" not in ch for ch in payload["chapters"])

    def test_golden_unique_ids_and_finding_id_resolution(self) -> None:
        payload = _load_golden()
        ids = [f["id"] for f in payload["findings"]]
        assert len(ids) == len(set(ids))
        by_id = {f["id"]: f for f in payload["findings"]}
        for chapter in payload["chapters"]:
            for fid in chapter["finding_ids"]:
                assert fid in by_id

    def test_golden_applyable_has_expected_old(self) -> None:
        payload = _load_golden()
        for finding in payload["findings"]:
            if finding["applyable"]:
                assert "expected_old" in finding["metadata"]

    def test_sample_report_matches_golden_shape(self) -> None:
        payload = report_to_payload(_sample_report())
        golden = _load_golden()
        # Drop zero-count keys that from_findings may omit vs fixture defaults.
        assert payload["mode"] == golden["mode"]
        assert payload["chapter_number"] == golden["chapter_number"]
        assert [f["id"] for f in payload["findings"]] == [
            f["id"] for f in golden["findings"]
        ]
        assert payload["chapters"][0]["finding_ids"] == golden["chapters"][0]["finding_ids"]
        assert validate_autonomicon_schema(payload) == []


class TestJsonExport:
    def test_export_json_stdout_only(self) -> None:
        buf = StringIO()
        text = export_json(_sample_report(), output=buf)
        data = json.loads(buf.getvalue())
        assert data["mode"] == "companion"
        assert '"mode": "companion"' in text

    def test_export_json_output_path(self, tmp_path: Path) -> None:
        path = tmp_path / "out.json"
        export_json(_sample_report(), output_path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["story_slug"] == "the-jailer-s-wound"

    def test_persist_companion_path(self, tmp_path: Path) -> None:
        (tmp_path / "config.yaml").write_text("format: json\n", encoding="utf-8")
        novel = tmp_path / "the-jailer-s-wound" / "chapters"
        novel.mkdir(parents=True)
        chapter = novel / "chapter-018.md"
        chapter.write_text("# Chapter 18\n\nHe  walked.\n", encoding="utf-8")

        report = _sample_report()
        report.manuscript_path = str(chapter)
        path = persist_report_json(report, project_root=tmp_path, manuscript_path=chapter)
        assert path.name == "companion-ch018.json"
        assert path.parent.name == "reports"
        assert path.parent.parent.name == "the-jailer-s-wound"
        assert json.loads(path.read_text(encoding="utf-8"))["chapter_number"] == 18

    def test_persist_analyze_timestamped(self, tmp_path: Path) -> None:
        (tmp_path / "config.yaml").write_text("format: json\n", encoding="utf-8")
        chapters = tmp_path / "story" / "chapters"
        chapters.mkdir(parents=True)
        report = CopyEditReport(
            ghostcopyeditor_version="0.1.0",
            mode="analyze",
            generated_at="2026-09-21T16:00:00+00:00",
            manuscript_path=str(chapters),
            manuscript_name="story",
            story_slug="story",
            chapter_number=None,
            summary=ReportSummary(chapters_scanned=0),
            findings=[],
            chapters=[],
        )
        stamp = datetime(2026, 9, 21, 16, 0, 0, tzinfo=timezone.utc)
        path = persist_report_json(
            report,
            project_root=tmp_path,
            manuscript_path=chapters,
            generated_at=stamp,
        )
        assert path.name == "analyze-20260921-160000.json"
        # Collision gets a suffix.
        path2 = report_persist_path(
            report,
            project_root=tmp_path,
            manuscript_path=chapters,
            generated_at=stamp,
        )
        assert path2.name == "analyze-20260921-160000-2.json"

    def test_validate_rejects_nested_findings_and_bad_ids(self) -> None:
        payload = _load_golden()
        payload["chapters"][0]["findings"] = []
        payload["chapters"][0]["finding_ids"].append("missing-id")
        errors = validate_autonomicon_schema(payload)
        assert any("must not include nested findings" in e for e in errors)
        assert any("does not resolve" in e for e in errors)

    def test_validate_missing_keys_and_duplicate_ids(self) -> None:
        errors = validate_autonomicon_schema({"mode": "companion"})
        assert any("missing top-level keys" in e for e in errors)

        payload = _load_golden()
        payload["findings"].append(dict(payload["findings"][0]))
        errors = validate_autonomicon_schema(payload)
        assert any("unique" in e for e in errors)

        payload = _load_golden()
        payload["summary"] = "nope"
        assert any("summary must be an object" in e for e in validate_autonomicon_schema(payload))

        payload = _load_golden()
        payload["findings"] = "nope"
        assert any("findings must be a list" in e for e in validate_autonomicon_schema(payload))

        payload = _load_golden()
        payload["chapters"] = "nope"
        assert any("chapters must be a list" in e for e in validate_autonomicon_schema(payload))

        payload = _load_golden()
        payload["findings"][0]["applyable"] = True
        payload["findings"][0]["metadata"] = {}
        payload["findings"][0]["location"]["excerpt"] = ""
        assert any("expected_old" in e for e in validate_autonomicon_schema(payload))

        payload = _load_golden()
        payload["findings"].append({"message": "no id"})
        payload["findings"].append({"message": "also no id"})
        assert validate_autonomicon_schema(payload) == []

        payload = _load_golden()
        payload["findings"][0]["rule_id"] = "echo.local_repeat"
        payload["chapters"][0]["finding_ids"].append("missing-id")
        errors = validate_autonomicon_schema(payload)
        assert errors == ["echo notes must not sit in findings; use may_look"]

        payload = _load_golden()
        payload["may_look"] = "nope"
        assert any("may_look must be a list" in e for e in validate_autonomicon_schema(payload))

    def test_persist_also_path(self, tmp_path: Path) -> None:
        (tmp_path / "config.yaml").write_text("format: json\n", encoding="utf-8")
        chapter = tmp_path / "chapter-009.md"
        chapter.write_text("# Nine\n", encoding="utf-8")
        report = _sample_report()
        report.manuscript_path = str(chapter)
        report.chapter_number = 9
        also = tmp_path / "extra" / "copy.json"
        path = persist_report_json(
            report, project_root=tmp_path, manuscript_path=chapter, also_path=also
        )
        assert path.name == "companion-ch009.json"
        assert also.is_file()

    def test_failed_second_write_restores_the_first(self, tmp_path: Path) -> None:
        (tmp_path / "config.yaml").write_text("format: json\n", encoding="utf-8")
        chapter = tmp_path / "chapter-009.md"
        chapter.write_text("# Nine\n", encoding="utf-8")
        report = _sample_report()
        report.manuscript_path = str(chapter)
        report.chapter_number = 9
        path = persist_report_json(
            report, project_root=tmp_path, manuscript_path=chapter
        )
        original = path.read_text(encoding="utf-8")
        also = tmp_path / "extra" / "copy.json"
        real_write = Path.write_text

        def fail_second(self: Path, text: str, *args: object, **kwargs: object) -> int:
            if self == also:
                raise OSError("disk full")
            return real_write(self, text, *args, **kwargs)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(Path, "write_text", fail_second)
        try:
            with pytest.raises(OSError, match="disk full"):
                persist_report_json(
                    report,
                    project_root=tmp_path,
                    manuscript_path=chapter,
                    also_path=also,
                )
        finally:
            monkeypatch.undo()
        assert path.read_text(encoding="utf-8") == original
        assert not also.exists()

    def test_export_json_defaults_to_stdout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        buf = StringIO()
        monkeypatch.setattr("ghostcopyeditor.report.json_export.sys.stdout", buf)
        export_json(_sample_report())
        assert json.loads(buf.getvalue())["mode"] == "companion"


class TestTerminalReport:
    def test_render_report_includes_location_and_engine(self) -> None:
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=100, color_system=None)
        render_report(_sample_report(), console=console)
        text = buf.getvalue()
        assert "Ch 18:L42" in text
        assert "Double space" in text
        assert "deterministic" in text
        assert "Overview" in text

    def test_render_analyze_rollup_table(self) -> None:
        report = CopyEditReport(
            ghostcopyeditor_version="0.1.0",
            mode="analyze",
            generated_at="2026-09-21T16:00:00+00:00",
            manuscript_path="/story/chapters",
            manuscript_name="story",
            story_slug="story",
            chapter_number=None,
            summary=ReportSummary(
                total_findings=1,
                chapters_scanned=2,
                by_severity={"error": 1, "warning": 0, "suggestion": 0, "info": 0},
            ),
            findings=[
                Finding(
                    id="det-c001-0001",
                    category=Category.GRAMMAR,
                    severity=Severity.ERROR,
                    message="Double space.",
                    location=Location(
                        chapter_number=1,
                        chapter_path="/c1.md",
                        line_start=3,
                        char_start=0,
                        char_end=2,
                        excerpt="  ",
                    ),
                    engine=Engine.DETERMINISTIC,
                )
            ],
            chapters=[
                ChapterResult(1, "/c1.md", "One", ["det-c001-0001"]),
                ChapterResult(2, "/c2.md", "Two", []),
            ],
        )
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=100, color_system=None)
        render_report(report, console=console)
        text = buf.getvalue()
        assert "Per-chapter rollup" in text
        assert "One" in text
        assert "Two" in text

    def test_render_default_console_and_apply_flag(self) -> None:
        report = _sample_report()
        report.apply = True
        # Exercise default Console() path without asserting on real TTY output.
        render_report(report, console=Console(file=StringIO(), force_terminal=False, width=80))

    def test_render_warnings_and_no_line(self) -> None:
        report = _sample_report()
        report.warnings = ["skipped a fix"]
        old = report.findings[0]
        report.findings[0] = Finding(
            id=old.id,
            category=old.category,
            severity=old.severity,
            message=old.message,
            suggestion=old.suggestion,
            engine=old.engine,
            rule_id=old.rule_id,
            applyable=old.applyable,
            replacement=old.replacement,
            location=Location(
                chapter_number=18,
                chapter_path=old.location.chapter_path,
                excerpt=old.location.excerpt,
            ),
            metadata=old.metadata,
        )
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=100, color_system=None)
        render_report(report, console=console)
        text = buf.getvalue()
        assert "Warnings" in text
        assert "skipped a fix" in text
        assert "Ch 18" in text

    def test_render_truncates_with_more(self) -> None:
        findings = [
            Finding(
                id=f"det-c001-{i:04d}",
                category=Category.GRAMMAR,
                severity=Severity.ERROR,
                message=f"Issue {i}",
                location=Location(chapter_number=1, chapter_path="/c.md", line_start=i),
                engine=Engine.DETERMINISTIC,
            )
            for i in range(1, 6)
        ]
        report = CopyEditReport(
            ghostcopyeditor_version="0.1.0",
            mode="companion",
            generated_at="2026-09-21T16:00:00+00:00",
            manuscript_path="/c.md",
            manuscript_name="story · Chapter 1",
            story_slug="story",
            chapter_number=1,
            summary=ReportSummary.from_findings(findings, chapters_scanned=1),
            findings=findings,
            chapters=[ChapterResult(1, "/c.md", "One", [f.id for f in findings])],
        )
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=100, color_system=None)
        render_report(report, console=console, max_findings=2)
        assert "and 3 more" in buf.getvalue()
