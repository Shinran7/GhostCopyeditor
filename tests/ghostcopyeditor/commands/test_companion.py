"""Tests for companion command wiring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ghostcopyeditor.cli import app

runner = CliRunner()


class TestCompanionCommand:
    def test_companion_json_includes_chapter_rollup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        chapter = tmp_path / "story" / "chapters" / "chapter-018.md"
        chapter.parent.mkdir(parents=True)
        chapter.write_text("# Chapter 18\n\nHe walked.\n", encoding="utf-8")

        result = runner.invoke(app, ["companion", str(chapter), "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["mode"] == "companion"
        assert data["chapter_number"] == 18
        assert data["findings"] == []
        assert len(data["chapters"]) == 1
        assert data["chapters"][0]["chapter_number"] == 18
        assert data["chapters"][0]["finding_ids"] == []
        assert data["chapters"][0]["title"] == "Chapter 18"
        assert "findings" not in data["chapters"][0]
        assert data["summary"]["chapters_scanned"] == 1

    def test_companion_rejects_bad_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        bad = tmp_path / "notes.md"
        bad.write_text("# Notes\n", encoding="utf-8")
        result = runner.invoke(app, ["companion", str(bad), "--format", "json"])
        assert result.exit_code == 1

    def test_companion_writes_output_and_terminal(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        chapter = tmp_path / "chapter-002.md"
        chapter.write_text("# Two\n", encoding="utf-8")
        out = tmp_path / "report.json"
        result = runner.invoke(app, ["companion", str(chapter), "-o", str(out)])
        assert result.exit_code == 0
        assert "companion complete" in result.output.lower()
        assert out.is_file()
