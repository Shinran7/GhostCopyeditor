"""Tests for the CLI module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ghostcopyeditor.cli import app

runner = CliRunner()

REQUIRED_JSON_KEYS = {
    "ghostcopyeditor_version",
    "mode",
    "generated_at",
    "manuscript_path",
    "manuscript_name",
    "story_slug",
    "chapter_number",
    "summary",
    "findings",
    "chapters",
    "warnings",
    "typesafe_enabled",
    "llm_enabled",
    "apply",
}


class TestHelp:
    def test_help_lists_companion_and_analyze(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "companion" in result.output
        assert "analyze" in result.output
        assert "init" in result.output
        assert "config" in result.output


class TestInit:
    def test_init_creates_config_and_state_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        target = tmp_path / "my-novel"
        target.mkdir()
        result = runner.invoke(app, ["init", str(target)])
        assert result.exit_code == 0
        assert (target / "config.yaml").exists()
        assert (target / ".ghostcopyeditor").is_dir()
        text = (target / "config.yaml").read_text(encoding="utf-8")
        assert "model: gemini-3.8-flash" in text
        assert "typesafe_enabled: false" in text
        assert "llm_enabled: false" in text
        assert "secrets/llm.env" in result.output

    def test_init_duplicate_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.yaml").write_text("format: terminal\n", encoding="utf-8")
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 1


class TestConfigShow:
    def test_config_show(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["config"])
        assert result.exit_code == 0
        assert "typesafe_enabled" in result.output
        assert "llm_enabled" in result.output


class TestConfigSet:
    def test_config_set_valid_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "config.yaml").write_text(
            "typesafe_enabled: false\nllm_enabled: false\n", encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["config", "set", "typesafe_enabled", "true"])
        assert result.exit_code == 0
        assert "True" in result.output
        loaded = (tmp_path / "config.yaml").read_text(encoding="utf-8")
        assert "typesafe_enabled: true" in loaded

    def test_config_set_invalid_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "config.yaml").write_text("format: terminal\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["config", "set", "nonexistent", "value"])
        assert result.exit_code == 1

    def test_config_set_without_config_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "ghostcopyeditor.paths.find_project_root", lambda start=None: None
        )
        result = runner.invoke(app, ["config", "set", "llm_enabled", "true"])
        assert result.exit_code == 1


class TestCompanionStub:
    def test_companion_json_exit_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        chapter = tmp_path / "story" / "chapters" / "chapter-018.md"
        chapter.parent.mkdir(parents=True)
        chapter.write_text("# Chapter 18\n\nHe walked.\n", encoding="utf-8")

        result = runner.invoke(
            app, ["companion", str(chapter), "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert REQUIRED_JSON_KEYS <= set(data)
        assert data["mode"] == "companion"
        assert data["findings"] == []
        assert data["summary"]["total_findings"] == 0
        assert data["chapter_number"] == 18
        assert data["typesafe_enabled"] is False
        assert data["llm_enabled"] is False
        assert len(data["chapters"]) == 1
        assert data["chapters"][0]["finding_ids"] == []

    def test_companion_missing_path_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        missing = tmp_path / "nope" / "chapter-001.md"
        result = runner.invoke(app, ["companion", str(missing), "--format", "json"])
        assert result.exit_code == 1


class TestAnalyzeStub:
    def test_analyze_json_exit_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        chapters = tmp_path / "story" / "chapters"
        chapters.mkdir(parents=True)
        (chapters / "chapter-001.md").write_text("# One\n", encoding="utf-8")

        result = runner.invoke(
            app, ["analyze", str(chapters), "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert REQUIRED_JSON_KEYS <= set(data)
        assert data["mode"] == "analyze"
        assert data["findings"] == []
        assert data["chapter_number"] is None

    def test_analyze_terminal_exit_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        chapters = tmp_path / "chapters"
        chapters.mkdir()
        (chapters / "chapter-001.md").write_text("# One\n", encoding="utf-8")
        result = runner.invoke(app, ["analyze", str(chapters)])
        assert result.exit_code == 0
        assert "analyze complete" in result.output.lower()


class TestConfigSetCoercion:
    def test_config_set_numeric_and_null(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runner.invoke(app, ["init", str(tmp_path)])
        monkeypatch.chdir(tmp_path)
        r1 = runner.invoke(app, ["config", "set", "temperature", "0.5"])
        assert r1.exit_code == 0
        r2 = runner.invoke(app, ["config", "set", "echo_window_words", "50"])
        assert r2.exit_code == 0
        r3 = runner.invoke(app, ["config", "set", "max_tokens", "null"])
        assert r3.exit_code == 0
        text = (tmp_path / "config.yaml").read_text(encoding="utf-8")
        assert "temperature: 0.5" in text
        assert "echo_window_words: 50" in text
        assert "max_tokens: null" in text


class TestCompanionTerminalMissing:
    def test_companion_missing_terminal_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        missing = tmp_path / "missing.md"
        result = runner.invoke(app, ["companion", str(missing)])
        assert result.exit_code == 1
