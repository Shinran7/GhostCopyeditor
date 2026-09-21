"""Tests for markdown_loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.ingestion.markdown_loader import (
    chapter_number_from_filename,
    extract_title,
    load_markdown,
)


def _write_chapter(directory: Path, num: int, body: str) -> Path:
    path = directory / f"chapter-{num:03d}.md"
    path.write_text(body, encoding="utf-8")
    return path


class TestMarkdownLoader:
    def test_load_single_chapter_file(self, tmp_path: Path) -> None:
        chapters = tmp_path / "chapters"
        chapters.mkdir()
        path = _write_chapter(
            chapters,
            18,
            "---\ntitle: Jailer\n---\n\n# Chapter 18\n\nHe walked.\n",
        )
        loaded = load_markdown(path)
        assert len(loaded) == 1
        ch = loaded[0]
        assert isinstance(ch, Chapter)
        assert ch.chapter_number == 18
        assert ch.title == "Chapter 18"
        assert ch.content.startswith("---\n")
        assert "He walked." in ch.content
        assert ch.source_path == path.resolve()

    def test_load_directory_orders_by_number(self, tmp_path: Path) -> None:
        chapters = tmp_path / "chapters"
        chapters.mkdir()
        _write_chapter(chapters, 2, "# Two\n")
        _write_chapter(chapters, 10, "# Ten\n")
        _write_chapter(chapters, 1, "# One\n")
        (chapters / "notes.md").write_text("# ignore me\n", encoding="utf-8")

        loaded = load_markdown(chapters)
        assert [c.chapter_number for c in loaded] == [1, 2, 10]
        assert all(c.source_path.name.startswith("chapter-") for c in loaded)

    def test_load_missing_path(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_markdown(tmp_path / "nope.md")

    def test_load_empty_directory(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="No chapter"):
            load_markdown(tmp_path)

    def test_non_md_file_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "chapter-001.txt"
        path.write_text("x", encoding="utf-8")
        with pytest.raises(ValueError, match=r"\.md"):
            load_markdown(path)

    def test_chapter_number_from_filename(self) -> None:
        assert chapter_number_from_filename(Path("chapter-018.md")) == 18
        assert chapter_number_from_filename(Path("CHAPTER-3.MD")) == 3
        assert chapter_number_from_filename(Path("prologue.md")) is None

    def test_extract_title_fallback(self) -> None:
        assert extract_title("no heading\n", fallback="stem") == "stem"
        assert extract_title("# Real Title\n", fallback="stem") == "Real Title"

    def test_unicode_codepoints_in_content(self, tmp_path: Path) -> None:
        path = tmp_path / "chapter-001.md"
        path.write_text("# Hi\n\ncafé 😀\n", encoding="utf-8")
        ch = load_markdown(path)[0]
        idx = ch.content.index("😀")
        assert ch.content[idx] == "😀"
        assert len("😀") == 1
