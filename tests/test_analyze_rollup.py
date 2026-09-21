"""Analyze rollup: unique finding IDs across chapters, exit 0, stderr progress."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ghostcopyeditor.cli import app
from ghostcopyeditor.report import validate_autonomicon_schema

runner = CliRunner()


def _write_chapter(directory: Path, num: int, body: str) -> Path:
    path = directory / f"chapter-{num:03d}.md"
    path.write_text(body, encoding="utf-8")
    return path


class TestAnalyzeRollup:
    def test_unique_ids_across_chapters_with_same_rule(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.yaml").write_text(
            "format: json\ntypesafe_enabled: false\nllm_enabled: false\n",
            encoding="utf-8",
        )
        chapters = tmp_path / "story" / "chapters"
        chapters.mkdir(parents=True)
        # Same deterministic issue in both chapters.
        _write_chapter(chapters, 1, "# One\n\nHe  walked home.\n")
        _write_chapter(chapters, 2, "# Two\n\nShe  waited there.\n")

        result = runner.invoke(app, ["analyze", str(chapters), "--format", "json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert validate_autonomicon_schema(data) == []

        ids = [f["id"] for f in data["findings"]]
        assert len(ids) == len(set(ids))
        assert any(i.startswith("det-c001-") for i in ids)
        assert any(i.startswith("det-c002-") for i in ids)

        by_id = {f["id"]: f for f in data["findings"]}
        for chapter in data["chapters"]:
            assert "findings" not in chapter
            for fid in chapter["finding_ids"]:
                assert fid in by_id
                assert by_id[fid]["location"]["chapter_number"] == chapter["chapter_number"]

        # Persist under flat .ghostcopyeditor/<story>/reports/
        persisted = list((tmp_path / ".ghostcopyeditor").rglob("analyze-*.json"))
        assert persisted, "expected analyze-*.json under .ghostcopyeditor"

    def test_exit_zero_with_findings_and_stderr_progress(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.yaml").write_text(
            "format: json\ntypesafe_enabled: false\nllm_enabled: false\n",
            encoding="utf-8",
        )
        chapters = tmp_path / "chapters"
        chapters.mkdir()
        _write_chapter(chapters, 3, "# Three\n\nHe  walked.\n")

        result = runner.invoke(app, ["analyze", str(chapters), "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["summary"]["total_findings"] >= 1
        # Progress / persist note on stderr, not mixed into stdout JSON.
        assert "ghostcopyeditor analyze" in result.stderr.lower() or "Wrote" in result.stderr
        # Stdout must parse as a single JSON object (already did).
        assert data["mode"] == "analyze"
        assert data["chapter_number"] is None

    def test_companion_exit_zero_with_findings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.yaml").write_text(
            "format: json\ntypesafe_enabled: false\nllm_enabled: false\n",
            encoding="utf-8",
        )
        chapter = tmp_path / "story" / "chapters" / "chapter-018.md"
        chapter.parent.mkdir(parents=True)
        chapter.write_text("# Chapter 18\n\nHe  walked.\n", encoding="utf-8")

        result = runner.invoke(app, ["companion", str(chapter), "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["summary"]["total_findings"] >= 1
        assert validate_autonomicon_schema(data) == []
        persisted = list((tmp_path / ".ghostcopyeditor").rglob("companion-ch018.json"))
        assert len(persisted) == 1

    def test_terminal_analyze_shows_rollup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.yaml").write_text(
            "format: terminal\ntypesafe_enabled: false\nllm_enabled: false\n",
            encoding="utf-8",
        )
        chapters = tmp_path / "story" / "chapters"
        chapters.mkdir(parents=True)
        _write_chapter(chapters, 1, "# One\n\nHe  walked.\n")
        _write_chapter(chapters, 2, "# Two\n\nClean prose here.\n")

        result = runner.invoke(app, ["analyze", str(chapters)])
        assert result.exit_code == 0
        assert "Per-chapter rollup" in result.output or "Overview" in result.output
