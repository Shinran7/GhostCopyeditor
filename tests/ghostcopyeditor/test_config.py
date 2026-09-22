"""Tests for the config module."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostcopyeditor.config import GhostCopyeditorConfig


class TestGhostCopyeditorConfig:
    def test_defaults(self) -> None:
        cfg = GhostCopyeditorConfig()
        assert cfg.model == "gemini-3.8-flash"
        assert cfg.format == "terminal"
        assert cfg.temperature == 0.2
        assert cfg.max_tokens is None
        assert cfg.typesafe_enabled is True
        assert cfg.llm_enabled is True
        assert cfg.typesafe_confidence_floor == 0.55
        assert cfg.typesafe_noul_positive_threshold == 0.65
        assert cfg.apply_default is False
        assert cfg.echo_window_words == 40
        assert cfg.echo_min_repeats == 3
        assert cfg.echo_phrase_min_n == 3
        assert cfg.echo_phrase_max_n == 4
        assert cfg.echo_phrase_max_gap == 2
        assert cfg.wordiness_enabled is True

    def test_save_includes_engine_flags(self, tmp_path: Path) -> None:
        cfg = GhostCopyeditorConfig(typesafe_enabled=True, llm_enabled=True)
        path = cfg.save(tmp_path)
        text = path.read_text(encoding="utf-8")
        assert "typesafe_enabled: true" in text
        assert "llm_enabled: true" in text
        assert "typesafe_confidence_floor: 0.55" in text
        assert "echo_window_words: 40" in text
        assert "echo_phrase_min_n: 3" in text
        assert "echo_phrase_max_gap: 2" in text
        loaded = GhostCopyeditorConfig.load(tmp_path)
        assert loaded.typesafe_enabled is True
        assert loaded.llm_enabled is True

    def test_save_writes_gemini_default(self, tmp_path: Path) -> None:
        cfg = GhostCopyeditorConfig()
        path = cfg.save(tmp_path)
        text = path.read_text(encoding="utf-8")
        assert "model: gemini-3.8-flash" in text
        assert "temperature: 0.2" in text

    def test_save_and_load(self, tmp_path: Path) -> None:
        cfg = GhostCopyeditorConfig(model="gpt-4o", temperature=0.7, llm_enabled=True)
        cfg.save(tmp_path)
        loaded = GhostCopyeditorConfig.load(tmp_path)
        assert loaded.model == "gpt-4o"
        assert loaded.temperature == 0.7
        assert loaded.llm_enabled is True

    def test_load_no_config_returns_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        cfg = GhostCopyeditorConfig.load(tmp_path)
        assert cfg.model == "gemini-3.8-flash"
        assert cfg.typesafe_enabled is True
        assert cfg.llm_enabled is True

    def test_load_from_child_dir(self, tmp_path: Path) -> None:
        cfg = GhostCopyeditorConfig(model="claude-sonnet-4-20250514")
        cfg.save(tmp_path)

        child = tmp_path / "manuscripts" / "novel.md"
        child.parent.mkdir(parents=True)
        child.write_text("# Ch1", encoding="utf-8")
        loaded = GhostCopyeditorConfig.load(child)
        assert loaded.model == "claude-sonnet-4-20250514"

    def test_model_dump(self) -> None:
        cfg = GhostCopyeditorConfig()
        data = cfg.model_dump()
        assert "model" in data
        assert "format" in data
        assert "typesafe_enabled" in data
        assert "llm_enabled" in data
        assert "temperature" in data
        assert "max_tokens" in data
