"""Tests for path resolution helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostcopyeditor.paths import (
    chapter_number_for,
    config_path,
    find_project_root,
    find_secrets_env,
    manuscript_display_name,
    package_project_root,
    reports_dir,
    story_slug_for,
    story_state_dir_for,
)


class TestFindProjectRoot:
    def test_finds_root_with_config_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "config.yaml").write_text("format: terminal\n", encoding="utf-8")
        child = tmp_path / "a" / "b"
        child.mkdir(parents=True)
        assert find_project_root(child) == tmp_path
        assert config_path(child) == tmp_path / "config.yaml"

    def test_returns_none_when_absent(self, tmp_path: Path) -> None:
        assert find_project_root(tmp_path) is None


class TestStorySlug:
    def test_story_slug_skips_chapters(self, tmp_path: Path) -> None:
        chapter = tmp_path / "the-jailer-s-wound" / "chapters" / "chapter-018.md"
        chapter.parent.mkdir(parents=True)
        chapter.write_text("x", encoding="utf-8")
        assert story_slug_for(chapter) == "the-jailer-s-wound"
        assert "Chapter 18" in manuscript_display_name(chapter)

    def test_story_slug_for_plain_file_and_dir(self, tmp_path: Path) -> None:
        plain = tmp_path / "notes.md"
        plain.write_text("hi", encoding="utf-8")
        assert story_slug_for(plain) == "notes"
        assert manuscript_display_name(plain) == "notes"
        folder = tmp_path / "bay-four" / "chapters"
        folder.mkdir(parents=True)
        assert story_slug_for(folder) == "bay-four"
        assert manuscript_display_name(folder) == "bay-four"


class TestStateDirs:
    def test_state_and_reports_helpers(self, tmp_path: Path) -> None:
        chapter = tmp_path / "novel" / "chapters" / "chapter-2.md"
        chapter.parent.mkdir(parents=True)
        chapter.write_text("x", encoding="utf-8")
        assert chapter_number_for(chapter) == 2
        assert chapter_number_for(tmp_path / "novel") is None
        state = story_state_dir_for(chapter, project_root=tmp_path)
        assert state == tmp_path / ".ghostcopyeditor" / "novel"
        assert state.is_dir()
        assert reports_dir(state) == state / "reports"


class TestFindSecretsEnv:
    def test_finds_secrets_file(self, tmp_path: Path) -> None:
        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        env_file = secrets_dir / "llm.env"
        env_file.write_text("OPENAI_API_KEY=test\n", encoding="utf-8")
        result = find_secrets_env(tmp_path)
        assert result is not None
        assert result == env_file

    def test_find_secrets_from_file_start(self, tmp_path: Path) -> None:
        secrets = tmp_path / "secrets"
        secrets.mkdir()
        env = secrets / "llm.env"
        env.write_text("X=1\n", encoding="utf-8")
        nested = tmp_path / "a" / "b.md"
        nested.parent.mkdir()
        nested.write_text("x", encoding="utf-8")
        assert find_secrets_env(nested) == env

    def test_returns_none_when_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "ghostcopyeditor.paths.package_project_root", lambda: None
        )
        assert find_secrets_env(tmp_path) is None


class TestPackageRoot:
    def test_package_project_root_points_at_checkout(self) -> None:
        root = package_project_root()
        assert root is not None
        assert (root / "pyproject.toml").is_file()
