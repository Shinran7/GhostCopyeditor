"""Finding model shared by every copy-edit engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from ghostcopyeditor.ingestion import Chapter


class Category(StrEnum):
    GRAMMAR = "grammar"
    GARBLED = "garbled"
    STYLE = "style"
    WORDINESS = "wordiness"
    ECHO = "echo"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    SUGGESTION = "suggestion"
    INFO = "info"


class Engine(StrEnum):
    DETERMINISTIC = "deterministic"
    TYPESAFE = "typesafe"
    LLM = "llm"


_ENGINE_PREFIX: dict[Engine, str] = {
    Engine.DETERMINISTIC: "det",
    Engine.TYPESAFE: "ts",
    Engine.LLM: "llm",
}


@dataclass(frozen=True)
class Location:
    """Span inside a chapter's full UTF-8-decoded file text.

    ``char_start`` / ``char_end`` are 0-based Unicode code-point offsets into
    ``Chapter.content`` (includes frontmatter). ``char_end`` is exclusive.
    ``line_start`` / ``line_end`` are 1-based when set.
    """

    chapter_number: int
    chapter_path: str
    line_start: int | None = None
    line_end: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    excerpt: str = ""


@dataclass
class Finding:
    """One copy-edit issue from any engine."""

    id: str
    category: Category
    severity: Severity
    message: str
    location: Location
    engine: Engine
    suggestion: str | None = None
    rule_id: str | None = None
    applyable: bool = False
    replacement: str | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for Autonomicon JSON (enums as strings)."""
        data = asdict(self)
        data["category"] = str(self.category)
        data["severity"] = str(self.severity)
        data["engine"] = str(self.engine)
        return data


def format_finding_id(engine: Engine, chapter_number: int, seq: int) -> str:
    """Build a report-unique id: ``{det|ts|llm}-c{NNN}-{seq:04d}``."""
    prefix = _ENGINE_PREFIX[engine]
    return f"{prefix}-c{chapter_number:03d}-{seq:04d}"


def assign_finding_ids(
    findings: list[Finding], chapter_number: int
) -> list[Finding]:
    """Assign report-unique IDs with a per-engine sequence restarting at 1."""
    counters: dict[Engine, int] = {
        Engine.DETERMINISTIC: 0,
        Engine.TYPESAFE: 0,
        Engine.LLM: 0,
    }
    for finding in findings:
        counters[finding.engine] += 1
        finding.id = format_finding_id(
            finding.engine, chapter_number, counters[finding.engine]
        )
    return findings


def line_number_at(content: str, char_offset: int) -> int:
    """1-based line number for a 0-based code-point offset into *content*."""
    if char_offset < 0:
        raise ValueError("char_offset must be >= 0")
    capped = min(char_offset, len(content))
    return content[:capped].count("\n") + 1


def location_from_span(
    chapter: Chapter,
    char_start: int,
    char_end: int,
    *,
    excerpt: str | None = None,
) -> Location:
    """Build a Location from exclusive-end code-point offsets into chapter content."""
    if char_start < 0 or char_end < char_start:
        raise ValueError("Invalid char span")
    text = chapter.content
    if excerpt is None:
        excerpt = text[char_start:char_end]
    return Location(
        chapter_number=chapter.chapter_number,
        chapter_path=str(chapter.source_path),
        line_start=line_number_at(text, char_start),
        line_end=line_number_at(text, max(char_end - 1, char_start)),
        char_start=char_start,
        char_end=char_end,
        excerpt=excerpt,
    )


__all__ = [
    "Category",
    "Engine",
    "Finding",
    "Location",
    "Severity",
    "assign_finding_ids",
    "format_finding_id",
    "line_number_at",
    "location_from_span",
]
