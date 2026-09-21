"""Load Markdown chapters from a file or chapter-*.md folder."""

from __future__ import annotations

from pathlib import Path

from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.paths import CHAPTER_FILE_RE

# Matches filenames like chapter-001.md, chapter-42.md, etc.
_CHAPTER_RE = CHAPTER_FILE_RE


def load_markdown(path: Path) -> list[Chapter]:
    """Load chapters from a Markdown file or directory of ``chapter-*.md``.

    Raises
    ------
    FileNotFoundError
        Path missing, or directory has no matching chapter files.
    ValueError
        Path is neither a ``.md`` file nor a directory.
    """
    path = path.resolve()

    if path.is_file():
        return [_load_single_file(path)]

    if path.is_dir():
        return _load_directory(path)

    msg = f"Path does not exist or is not a file/directory: {path}"
    raise FileNotFoundError(msg)


def chapter_number_from_filename(path: Path) -> int | None:
    """Return N from ``chapter-NNN.md``, or None if the name does not match."""
    match = _CHAPTER_RE.match(path.name)
    return int(match.group(1)) if match else None


def _load_single_file(path: Path) -> Chapter:
    """Treat a single ``.md`` file as one chapter."""
    if path.suffix.lower() != ".md":
        msg = f"Expected a .md file, got: {path.name}"
        raise ValueError(msg)

    # Full UTF-8 text including YAML frontmatter (coordinate space root).
    content = path.read_text(encoding="utf-8")
    title = extract_title(content, fallback=path.stem)
    chapter_number = chapter_number_from_filename(path) or 1
    return Chapter(
        title=title,
        content=content,
        chapter_number=chapter_number,
        source_path=path,
    )


def _load_directory(directory: Path) -> list[Chapter]:
    """Load ``chapter-*.md`` files from *directory*, sorted by chapter number."""
    numbered: list[tuple[int, Path]] = []
    for filepath in directory.glob("chapter-*.md"):
        num = chapter_number_from_filename(filepath)
        if num is not None:
            numbered.append((num, filepath))

    if not numbered:
        msg = f"No chapter-*.md files found in {directory}"
        raise FileNotFoundError(msg)

    numbered.sort(key=lambda item: item[0])
    chapters: list[Chapter] = []
    for num, filepath in numbered:
        content = filepath.read_text(encoding="utf-8")
        title = extract_title(content, fallback=filepath.stem)
        chapters.append(
            Chapter(
                title=title,
                content=content,
                chapter_number=num,
                source_path=filepath,
            )
        )
    return chapters


def extract_title(content: str, *, fallback: str) -> str:
    """Pull the first Markdown ``#`` heading as the chapter title."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip()
    return fallback


__all__ = [
    "chapter_number_from_filename",
    "extract_title",
    "load_markdown",
]
