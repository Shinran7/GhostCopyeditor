"""Path resolution for GhostCopyeditor config and per-story state.

Config:
    config.yaml in the project root (found by walking up from CWD or
    the manuscript path).

Per-story state (reports only; no vector DB):
    <project_root>/.ghostcopyeditor/<story-slug>/reports/
"""

from __future__ import annotations

import re
from pathlib import Path

# Directory names too generic to use as a story identifier.
_GENERIC_DIR_NAMES = {"chapters", "src", "manuscript", "manuscripts", "content", "text", "docs"}

# Matches chapter-001.md / chapter-18.md.
_CHAPTER_FILE_RE = re.compile(r"^chapter-(\d+)\.md$", re.IGNORECASE)


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk up from *start* (default: CWD) looking for ``config.yaml``.

    Returns the directory containing ``config.yaml``, or ``None``.
    """
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        if (directory / "config.yaml").is_file():
            return directory
    return None


def package_project_root() -> Path | None:
    """Return the GhostCopyeditor checkout/install root next to this package.

    Editable installs live at ``<repo>/ghostcopyeditor/paths.py``, so the repo
    root is ``parent.parent``. Used when Autonomicon (or another host) invokes
    ``ghostcopyeditor`` with a foreign CWD.
    """
    root = Path(__file__).resolve().parent.parent
    if (root / "config.yaml").is_file() or (root / "pyproject.toml").is_file():
        return root
    return None


def config_path(start: Path | None = None) -> Path | None:
    """Return the path to ``config.yaml``, or ``None`` if not found.

    Search order:
      1. Walk up from *start* (manuscript path)
      2. Walk up from CWD
      3. GhostCopyeditor package/checkout root (Autonomicon-hook safe)
    """
    root = find_project_root(start)
    if root is not None:
        return root / "config.yaml"
    if start is not None:
        root = find_project_root(Path.cwd())
        if root is not None:
            return root / "config.yaml"
    pkg = package_project_root()
    if pkg is not None and (pkg / "config.yaml").is_file():
        return pkg / "config.yaml"
    return None


def _slug_token(name: str) -> str:
    """Sanitize one path segment to a filesystem-safe slug token."""
    slug = re.sub(r"[^\w\-]", "-", name.lower()).strip("-")
    return slug or "manuscript"


def _skip_generic_parents(directory: Path) -> Path:
    """Walk up past generic folder names like ``chapters``."""
    current = directory
    while current.name.lower() in _GENERIC_DIR_NAMES and current.parent != current:
        current = current.parent
    return current


def story_slug_for(manuscript_path: Path) -> str:
    """Return the story slug under ``.ghostcopyeditor/<story>/``.

    For ``chapter-NNN.md`` this is the skipped parent of the file's directory.
    For directories, slug the skipped parent of that directory.
    Does not nest ``chapter-NNN`` segments (flatter than Ghostreader).
    """
    resolved = manuscript_path.resolve()
    if resolved.is_file():
        chapter_match = _CHAPTER_FILE_RE.match(resolved.name)
        if chapter_match:
            story_dir = _skip_generic_parents(resolved.parent)
            return _slug_token(story_dir.name)
        return _slug_token(resolved.stem)
    target = _skip_generic_parents(resolved)
    return _slug_token(target.name)


def manuscript_display_name(manuscript_path: Path) -> str:
    """Human label for reports and terminal headers.

    ``.../the-jailer-s-wound/chapters/chapter-018.md``
        → ``the-jailer-s-wound · Chapter 18``
    """
    resolved = manuscript_path.resolve()
    if resolved.is_file():
        chapter_match = _CHAPTER_FILE_RE.match(resolved.name)
        if chapter_match:
            story_dir = _skip_generic_parents(resolved.parent)
            return f"{story_dir.name} · Chapter {int(chapter_match.group(1))}"
        return resolved.stem
    target = _skip_generic_parents(resolved)
    return target.name


def chapter_number_for(manuscript_path: Path) -> int | None:
    """Return chapter number for ``chapter-NNN.md``, else ``None``."""
    resolved = manuscript_path.resolve()
    if not resolved.is_file():
        return None
    match = _CHAPTER_FILE_RE.match(resolved.name)
    if match is None:
        return None
    return int(match.group(1))


def _resolve_project_root(
    manuscript_path: Path, project_root: Path | None = None
) -> Path:
    """Resolve project root for state dirs.

    Order: explicit → manuscript config walk → CWD → package root → parent.
    """
    if project_root is not None:
        return project_root
    return (
        find_project_root(manuscript_path)
        or find_project_root(Path.cwd())
        or package_project_root()
        or manuscript_path.parent
    )


def story_state_dir_for(
    manuscript_path: Path, project_root: Path | None = None
) -> Path:
    """Return ``.ghostcopyeditor/<story>/``, creating it if needed."""
    root = _resolve_project_root(manuscript_path, project_root)
    state = root / ".ghostcopyeditor" / story_slug_for(manuscript_path)
    state.mkdir(parents=True, exist_ok=True)
    return state


def reports_dir(story_state_dir: Path) -> Path:
    """Return ``<story_state>/reports/`` (does not create)."""
    return story_state_dir / "reports"


def find_secrets_env(start: Path | None = None) -> Path | None:
    """Locate ``secrets/llm.env``.

    Walks from *start* (default CWD), then CWD if different, then the
    GhostCopyeditor package/checkout ``secrets/llm.env`` (Autonomicon-hook safe).
    """
    starts: list[Path] = []
    if start is not None:
        starts.append(start.resolve())
    cwd = Path.cwd().resolve()
    if not starts or starts[0] != cwd:
        starts.append(cwd)

    seen: set[Path] = set()
    for origin in starts:
        current = origin.parent if origin.is_file() else origin
        for directory in [current, *current.parents]:
            if directory in seen:
                continue
            seen.add(directory)
            candidate = directory / "secrets" / "llm.env"
            if candidate.is_file():
                return candidate

    pkg = package_project_root()
    if pkg is not None:
        candidate = pkg / "secrets" / "llm.env"
        if candidate.is_file():
            return candidate
    return None


__all__ = [
    "chapter_number_for",
    "config_path",
    "find_project_root",
    "find_secrets_env",
    "manuscript_display_name",
    "package_project_root",
    "reports_dir",
    "story_slug_for",
    "story_state_dir_for",
]
