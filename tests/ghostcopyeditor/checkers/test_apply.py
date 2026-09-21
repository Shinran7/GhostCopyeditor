"""Tests for safe deterministic --apply."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ghostcopyeditor.checkers.apply import (
    apply_findings,
    apply_to_content,
    is_apply_candidate,
)
from ghostcopyeditor.checkers.mechanics import MechanicsChecker
from ghostcopyeditor.cli import app
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Location,
    Severity,
)

runner = CliRunner()


def _chapter(text: str, path: Path | None = None, *, num: int = 1) -> Chapter:
    return Chapter(
        title="T",
        content=text,
        chapter_number=num,
        source_path=path or Path(f"/story/chapters/chapter-{num:03d}.md"),
    )


class TestApplyWriter:
    def test_reverse_offset_and_reverify(self) -> None:
        text = "He  walked , yes.\n"
        findings = MechanicsChecker().check(_chapter(text), GhostCopyeditorConfig())
        applyable = [f for f in findings if f.applyable]
        assert len(applyable) >= 2
        new_text, applied, warnings = apply_to_content(text, findings)
        assert applied >= 2
        assert "  " not in new_text
        assert " ," not in new_text
        assert warnings == []
        assert sum(1 for f in findings if f.metadata.get("applied")) == applied

    def test_mismatch_skips_and_warns(self) -> None:
        finding = Finding(
            id="det-c001-0001",
            category=Category.GRAMMAR,
            severity=Severity.ERROR,
            message="x",
            location=Location(
                chapter_number=1,
                chapter_path="x.md",
                char_start=0,
                char_end=2,
                excerpt="  ",
            ),
            engine=Engine.DETERMINISTIC,
            applyable=True,
            replacement=" ",
            metadata={"expected_old": "  "},
        )
        new_text, applied, warnings = apply_to_content("OK text", [finding])
        assert new_text == "OK text"
        assert applied == 0
        assert finding.applyable is False
        assert warnings

    def test_never_applies_llm(self) -> None:
        finding = Finding(
            id="llm-c001-0001",
            category=Category.GARBLED,
            severity=Severity.WARNING,
            message="x",
            location=Location(
                chapter_number=1,
                chapter_path="x.md",
                char_start=0,
                char_end=2,
                excerpt="He",
            ),
            engine=Engine.LLM,
            applyable=True,
            replacement="She",
            metadata={"expected_old": "He"},
        )
        assert not is_apply_candidate(finding)
        new_text, applied, _ = apply_to_content("He walked", [finding])
        assert new_text == "He walked"
        assert applied == 0

    def test_overlapping_refused(self) -> None:
        a = Finding(
            id="a",
            category=Category.GRAMMAR,
            severity=Severity.ERROR,
            message="a",
            location=Location(
                chapter_number=1, chapter_path="x.md", char_start=0, char_end=4
            ),
            engine=Engine.DETERMINISTIC,
            applyable=True,
            replacement="X",
            metadata={"expected_old": "He  "},
        )
        b = Finding(
            id="b",
            category=Category.GRAMMAR,
            severity=Severity.SUGGESTION,
            message="b",
            location=Location(
                chapter_number=1, chapter_path="x.md", char_start=2, char_end=6
            ),
            engine=Engine.DETERMINISTIC,
            applyable=True,
            replacement="Y",
            metadata={"expected_old": "  wa"},
        )
        new_text, applied, warnings = apply_to_content("He  walked", [a, b])
        assert applied == 1
        assert b.applyable is False
        assert any("overlapping" in w.lower() for w in warnings)
        assert new_text.startswith("X")

    def test_writes_file_and_keeps_pre_apply_coords(self, tmp_path: Path) -> None:
        path = tmp_path / "chapter-001.md"
        original = "He  walked.\n"
        path.write_text(original, encoding="utf-8")
        chapter = _chapter(original, path)
        findings = MechanicsChecker().check(chapter, GhostCopyeditorConfig())
        pre_start = findings[0].location.char_start
        applied, warnings = apply_findings([chapter], findings)
        assert applied >= 1
        assert warnings == []
        assert path.read_text(encoding="utf-8") == "He walked.\n"
        # Report coordinates stay pre-apply.
        assert findings[0].location.char_start == pre_start
        assert findings[0].metadata.get("applied") is True


class TestApplyCli:
    def test_apply_flag_rewrites_chapter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        chapter = tmp_path / "chapter-003.md"
        chapter.write_text("# Three\n\nHe  walked.\n", encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "companion",
                str(chapter),
                "--apply",
                "--format",
                "json",
                "--no-typesafe",
                "--no-llm",
            ],
        )
        assert result.exit_code == 0
        text = chapter.read_text(encoding="utf-8")
        assert "He walked." in text
        import json

        data = json.loads(result.stdout)
        assert data["apply"] is True
        assert data["summary"]["applied_count"] >= 1
        applied_findings = [f for f in data["findings"] if f["metadata"].get("applied")]
        assert applied_findings
        # Pre-apply coords present on applied finding.
        assert applied_findings[0]["location"]["char_start"] is not None

    def test_analyze_apply_rewrites_chapters(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        chapters = tmp_path / "chapters"
        chapters.mkdir()
        (chapters / "chapter-001.md").write_text("# One\n\nHe  walked.\n", encoding="utf-8")
        (chapters / "chapter-002.md").write_text("# Two\n\nShe  ran.\n", encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "analyze",
                str(chapters),
                "--apply",
                "--format",
                "json",
                "--no-typesafe",
                "--no-llm",
            ],
        )
        assert result.exit_code == 0
        assert "He walked." in (chapters / "chapter-001.md").read_text(encoding="utf-8")
        assert "She ran." in (chapters / "chapter-002.md").read_text(encoding="utf-8")
        import json

        data = json.loads(result.stdout)
        assert data["summary"]["applied_count"] >= 2
        assert data["summary"]["chapters_scanned"] == 2
