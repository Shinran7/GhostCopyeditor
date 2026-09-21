"""Markdown chapter ingest for GhostCopyeditor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chapter:
    """A single Markdown chapter loaded from disk."""

    title: str
    content: str
    chapter_number: int
    source_path: Path


__all__ = ["Chapter"]
