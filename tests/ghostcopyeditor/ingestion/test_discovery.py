"""Tests for companion/analyze discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostcopyeditor.ingestion.discovery import discover_analyze, discover_companion


def _write_chapter(directory: Path, num: int, body: str) -> Path:
    path = directory / f"chapter-{num:03d}.md"
    path.write_text(body, encoding="utf-8")
    return path


class TestCompanionDiscovery:
    def test_discovers_numbered_chapter(self, tmp_path: Path) -> None:
        chapters = tmp_path / "story" / "chapters"
        chapters.mkdir(parents=True)
        path = _write_chapter(chapters, 7, "# Seven\n\nProse.\n")
        result = discover_companion(path)
        assert result.chapter_number == 7
        assert result.chapter.content.endswith("Prose.\n")
        assert result.story_slug == "story"

    def test_rejects_non_chapter_name(self, tmp_path: Path) -> None:
        path = tmp_path / "prologue.md"
        path.write_text("# Prologue\n", encoding="utf-8")
        with pytest.raises(ValueError, match="chapter-NNN"):
            discover_companion(path)

    def test_rejects_directory(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="single chapter"):
            discover_companion(tmp_path)

    def test_missing_path(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            discover_companion(tmp_path / "chapter-001.md")


class TestAnalyzeDiscovery:
    def test_missing_path(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            discover_analyze(tmp_path / "no-such-dir")

    def test_orders_chapters(self, tmp_path: Path) -> None:
        chapters = tmp_path / "story" / "chapters"
        chapters.mkdir(parents=True)
        _write_chapter(chapters, 3, "# Three\n")
        _write_chapter(chapters, 1, "# One\n")
        result = discover_analyze(chapters)
        assert [c.chapter_number for c in result.chapters] == [1, 3]
        assert result.story_slug == "story"

    def test_nested_chapters_dir(self, tmp_path: Path) -> None:
        story = tmp_path / "my-novel"
        chapters = story / "chapters"
        chapters.mkdir(parents=True)
        _write_chapter(chapters, 1, "# One\n")
        result = discover_analyze(story)
        assert len(result.chapters) == 1
        assert result.chapters_dir == chapters.resolve()

    def test_rejects_file(self, tmp_path: Path) -> None:
        path = _write_chapter(tmp_path, 1, "# One\n")
        with pytest.raises(ValueError, match="folder"):
            discover_analyze(path)

    def test_empty_folder(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="No chapter"):
            discover_analyze(tmp_path)
