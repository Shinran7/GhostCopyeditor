"""Resolve companion vs analyze Markdown inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.ingestion.markdown_loader import load_markdown
from ghostcopyeditor.paths import (
    CHAPTER_FILE_RE,
    _skip_generic_parents,
    manuscript_display_name,
    story_slug_for,
)


@dataclass
class CompanionDiscovery:
    """Resolved single-chapter companion input."""

    path: Path
    chapter: Chapter
    story_slug: str
    story_dir: Path
    chapters_dir: Path
    chapter_number: int
    manuscript_name: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class AnalyzeDiscovery:
    """Resolved analyze chapter folder."""

    path: Path
    chapters: list[Chapter]
    story_slug: str
    story_dir: Path
    chapters_dir: Path
    manuscript_name: str
    warnings: list[str] = field(default_factory=list)


def _list_chapter_files(chapters_dir: Path) -> dict[int, Path]:
    found: dict[int, Path] = {}
    for filepath in sorted(chapters_dir.glob("chapter-*.md")):
        match = CHAPTER_FILE_RE.match(filepath.name)
        if match:
            found[int(match.group(1))] = filepath
    return found


def discover_companion(path: Path) -> CompanionDiscovery:
    """Require a single ``chapter-NNN.md`` file and load it.

    Raises
    ------
    FileNotFoundError
        Path missing.
    ValueError
        Path is not a file, or filename is not ``chapter-NNN.md``.
    """
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not path.is_file():
        raise ValueError(
            f"Companion requires a single chapter-NNN.md file; got directory '{path}'."
        )
    match = CHAPTER_FILE_RE.match(path.name)
    if not match:
        raise ValueError(
            f"Companion requires a file named chapter-NNN.md; got '{path.name}'."
        )

    chapter = load_markdown(path)[0]
    chapters_dir = path.parent
    story_dir = _skip_generic_parents(chapters_dir)
    return CompanionDiscovery(
        path=path,
        chapter=chapter,
        story_slug=story_slug_for(path),
        story_dir=story_dir,
        chapters_dir=chapters_dir,
        chapter_number=int(match.group(1)),
        manuscript_name=manuscript_display_name(path),
    )


def discover_analyze(path: Path) -> AnalyzeDiscovery:
    """Discover and order ``chapter-*.md`` files for analyze.

    Accepts a chapters directory or a story directory containing ``chapters/``.

    Raises
    ------
    FileNotFoundError
        Path missing, or no ``chapter-*.md`` files found.
    ValueError
        Path is a lone file (analyze expects a folder).
    """
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if path.is_file():
        raise ValueError(
            f"Analyze expects a chapter folder (or story dir with chapters/); "
            f"got file '{path.name}'. Use companion for a single chapter-NNN.md."
        )

    chapters_dir = path
    files = _list_chapter_files(chapters_dir)
    if not files:
        nested = path / "chapters"
        if nested.is_dir() and _list_chapter_files(nested):
            chapters_dir = nested
            files = _list_chapter_files(chapters_dir)
    if not files:
        raise FileNotFoundError(
            f"No chapter-*.md files found in {path}."
        )

    chapters = load_markdown(chapters_dir)
    story_dir = _skip_generic_parents(chapters_dir)
    return AnalyzeDiscovery(
        path=path,
        chapters=chapters,
        story_slug=story_slug_for(path),
        story_dir=story_dir,
        chapters_dir=chapters_dir,
        manuscript_name=manuscript_display_name(path),
    )


__all__ = [
    "AnalyzeDiscovery",
    "CompanionDiscovery",
    "discover_analyze",
    "discover_companion",
]
