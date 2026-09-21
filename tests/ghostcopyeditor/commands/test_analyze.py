"""Tests for analyze command wiring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ghostcopyeditor.cli import app

runner = CliRunner()


def _write_chapter(directory: Path, num: int, body: str) -> Path:
    path = directory / f"chapter-{num:03d}.md"
    path.write_text(body, encoding="utf-8")
    return path


class TestAnalyzeCommand:
    def test_analyze_json_lists_chapters(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        chapters = tmp_path / "story" / "chapters"
        chapters.mkdir(parents=True)
        _write_chapter(chapters, 1, "# One\n")
        _write_chapter(chapters, 2, "# Two\n")

        result = runner.invoke(app, ["analyze", str(chapters), "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["mode"] == "analyze"
        assert data["chapter_number"] is None
        assert data["summary"]["chapters_scanned"] == 2
        assert [c["chapter_number"] for c in data["chapters"]] == [1, 2]
        assert all(c["finding_ids"] == [] for c in data["chapters"])

    def test_analyze_missing_path_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            app, ["analyze", str(tmp_path / "missing"), "--format", "json"]
        )
        assert result.exit_code == 1

    def test_analyze_file_path_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        path = _write_chapter(tmp_path, 1, "# One\n")
        result = runner.invoke(app, ["analyze", str(path)])
        assert result.exit_code == 1

    def test_analyze_writes_output_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        chapters = tmp_path / "chapters"
        chapters.mkdir()
        _write_chapter(chapters, 1, "# One\n")
        out = tmp_path / "out" / "report.json"
        result = runner.invoke(
            app, ["analyze", str(chapters), "--format", "json", "-o", str(out)]
        )
        assert result.exit_code == 0
        assert out.is_file()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["mode"] == "analyze"
