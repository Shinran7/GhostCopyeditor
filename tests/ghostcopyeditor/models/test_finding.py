"""Tests for Finding / Location / ID helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Location,
    Severity,
    assign_finding_ids,
    format_finding_id,
    line_number_at,
    location_from_span,
)


def _chapter(text: str, *, num: int = 18) -> Chapter:
    return Chapter(
        title=f"Chapter {num}",
        content=text,
        chapter_number=num,
        source_path=Path(f"/story/chapters/chapter-{num:03d}.md"),
    )


class TestFindingIds:
    def test_format_finding_id(self) -> None:
        assert format_finding_id(Engine.DETERMINISTIC, 18, 1) == "det-c018-0001"
        assert format_finding_id(Engine.TYPESAFE, 3, 2) == "ts-c003-0002"
        assert format_finding_id(Engine.LLM, 1, 10) == "llm-c001-0010"

    def test_assign_finding_ids_per_engine(self) -> None:
        loc = Location(chapter_number=18, chapter_path="x.md")
        findings = [
            Finding(
                id="",
                category=Category.GRAMMAR,
                severity=Severity.ERROR,
                message="a",
                location=loc,
                engine=Engine.DETERMINISTIC,
            ),
            Finding(
                id="",
                category=Category.GARBLED,
                severity=Severity.WARNING,
                message="b",
                location=loc,
                engine=Engine.LLM,
            ),
            Finding(
                id="",
                category=Category.GRAMMAR,
                severity=Severity.ERROR,
                message="c",
                location=loc,
                engine=Engine.DETERMINISTIC,
            ),
            Finding(
                id="",
                category=Category.STYLE,
                severity=Severity.SUGGESTION,
                message="d",
                location=loc,
                engine=Engine.TYPESAFE,
            ),
        ]
        assign_finding_ids(findings, 18)
        assert [f.id for f in findings] == [
            "det-c018-0001",
            "llm-c018-0001",
            "det-c018-0002",
            "ts-c018-0001",
        ]


class TestCoordinateSpace:
    def test_line_number_at(self) -> None:
        content = "a\nb\ncafé\n"
        assert line_number_at(content, 0) == 1
        assert line_number_at(content, 2) == 2
        assert line_number_at(content, content.index("c")) == 3

    def test_line_number_rejects_negative(self) -> None:
        with pytest.raises(ValueError):
            line_number_at("abc", -1)

    def test_location_from_span_includes_frontmatter_offsets(self) -> None:
        content = "---\ntitle: x\n---\n\n# Hi\n\nHe  walked.\n"
        chapter = _chapter(content)
        start = content.index("  ")
        end = start + 2
        loc = location_from_span(chapter, start, end)
        assert loc.char_start == start
        assert loc.char_end == end
        assert content[loc.char_start:loc.char_end] == "  "
        assert loc.excerpt == "  "
        assert loc.line_start == line_number_at(content, start)
        assert loc.chapter_number == 18

    def test_location_from_span_rejects_bad_span(self) -> None:
        chapter = _chapter("abc\n")
        with pytest.raises(ValueError):
            location_from_span(chapter, 2, 1)

    def test_unicode_code_point_offsets(self) -> None:
        content = "café 😀 end\n"
        chapter = _chapter(content, num=1)
        start = content.index("😀")
        end = start + 1
        loc = location_from_span(chapter, start, end)
        assert content[loc.char_start:loc.char_end] == "😀"


class TestFindingSerialization:
    def test_finding_to_dict(self) -> None:
        finding = Finding(
            id="det-c018-0001",
            category=Category.GRAMMAR,
            severity=Severity.ERROR,
            message="Double space.",
            location=Location(
                chapter_number=18,
                chapter_path="chapter-018.md",
                char_start=1,
                char_end=3,
                excerpt="  ",
            ),
            engine=Engine.DETERMINISTIC,
            rule_id="mech.double_space",
            applyable=True,
            replacement=" ",
            metadata={"expected_old": "  "},
        )
        data = finding.to_dict()
        assert data["category"] == "grammar"
        assert data["severity"] == "error"
        assert data["engine"] == "deterministic"
        assert data["location"]["char_start"] == 1
        assert data["metadata"]["expected_old"] == "  "
