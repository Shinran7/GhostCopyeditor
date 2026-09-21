"""Tests for secrets loading (llm.load_secrets)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ghostcopyeditor.llm import get_llm, load_secrets


class TestLoadSecrets:
    def test_loads_keys_from_env_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "llm.env").write_text(
            "# comment\n"
            "GHOSTCOPYEDITOR_TEST_KEY=from-file\n"
            "EMPTY_KEY=\n"
            "\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GHOSTCOPYEDITOR_TEST_KEY", raising=False)
        monkeypatch.setattr(
            "ghostcopyeditor.paths.find_secrets_env",
            lambda start=None: secrets_dir / "llm.env",
        )

        load_secrets()
        assert os.environ.get("GHOSTCOPYEDITOR_TEST_KEY") == "from-file"
        assert "EMPTY_KEY" not in os.environ

    def test_does_not_overwrite_existing_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "llm.env").write_text(
            "GHOSTCOPYEDITOR_TEST_KEY=from-file\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("GHOSTCOPYEDITOR_TEST_KEY", "already-set")
        monkeypatch.setattr(
            "ghostcopyeditor.paths.find_secrets_env",
            lambda start=None: secrets_dir / "llm.env",
        )

        load_secrets()
        assert os.environ["GHOSTCOPYEDITOR_TEST_KEY"] == "already-set"

    def test_noop_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "ghostcopyeditor.paths.find_secrets_env", lambda start=None: None
        )
        load_secrets()  # must not raise

    def test_get_llm_stub_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            get_llm()
