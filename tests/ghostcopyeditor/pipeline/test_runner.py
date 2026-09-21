"""Tests for end-of-pipeline dedupe_findings."""

from __future__ import annotations

import asyncio
from pathlib import Path

from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Location,
    Severity,
    assign_finding_ids,
)
from ghostcopyeditor.pipeline.runner import (
    dedupe_findings,
    run_analyze_pipeline,
    run_chapter_pipeline,
)


def _loc(
    *,
    chapter: int = 1,
    start: int | None = None,
    end: int | None = None,
) -> Location:
    return Location(
        chapter_number=chapter,
        chapter_path="/x.md",
        char_start=start,
        char_end=end,
    )


def _finding(
    *,
    category: Category = Category.GRAMMAR,
    engine: Engine = Engine.DETERMINISTIC,
    message: str = "msg",
    start: int | None = 0,
    end: int | None = 5,
    chapter: int = 1,
) -> Finding:
    return Finding(
        id="",
        category=category,
        severity=Severity.ERROR,
        message=message,
        location=_loc(chapter=chapter, start=start, end=end),
        engine=engine,
    )


class TestDedupe:
    def test_overlap_half_or_more(self) -> None:
        a = _finding(start=0, end=10, message="first", engine=Engine.LLM)
        b = _finding(start=2, end=10, message="second", engine=Engine.DETERMINISTIC)
        kept = dedupe_findings([a, b])
        assert len(kept) == 1
        assert kept[0].engine == Engine.DETERMINISTIC

    def test_containment(self) -> None:
        outer = _finding(start=0, end=20, engine=Engine.TYPESAFE)
        inner = _finding(start=5, end=10, engine=Engine.DETERMINISTIC)
        kept = dedupe_findings([outer, inner])
        assert len(kept) == 1
        assert kept[0].engine == Engine.DETERMINISTIC

    def test_message_only_without_spans(self) -> None:
        a = _finding(start=None, end=None, message="Same Message")
        b = _finding(start=None, end=None, message="same   message")
        kept = dedupe_findings([a, b])
        assert len(kept) == 1

    def test_cross_category_keeps_both(self) -> None:
        a = _finding(category=Category.GRAMMAR, start=0, end=10)
        b = _finding(category=Category.GARBLED, start=0, end=10, engine=Engine.LLM)
        kept = dedupe_findings([a, b])
        assert len(kept) == 2

    def test_same_engine_keeps_first(self) -> None:
        a = _finding(message="a", start=0, end=10)
        b = _finding(message="b", start=0, end=10)
        kept = dedupe_findings([a, b])
        assert len(kept) == 1
        assert kept[0].message == "a"

    def test_pipeline_assigns_ids_then_dedupes(self) -> None:
        chapter = Chapter(
            title="T",
            content="He  walked.\n",
            chapter_number=18,
            source_path=Path("/story/chapters/chapter-018.md"),
        )
        findings = asyncio.run(
            run_chapter_pipeline(chapter, cfg=GhostCopyeditorConfig())
        )
        assert findings
        assert findings[0].id.startswith("det-c018-")
        ids = [f.id for f in findings]
        assert len(ids) == len(set(ids))

    def test_assign_then_dedupe_leaves_id_gaps_ok(self) -> None:
        findings = [
            _finding(message="a", start=0, end=10, engine=Engine.DETERMINISTIC),
            _finding(message="b", start=0, end=10, engine=Engine.LLM),
        ]
        assign_finding_ids(findings, 3)
        kept = dedupe_findings(findings)
        assert len(kept) == 1
        assert kept[0].id == "det-c003-0001"


class TestMultiChapterIds:
    def test_unique_across_chapters(self) -> None:
        chapters = [
            Chapter(
                title="One",
                content="He  walked.\n",
                chapter_number=1,
                source_path=Path("/s/chapter-001.md"),
            ),
            Chapter(
                title="Two",
                content="She  ran.\n",
                chapter_number=2,
                source_path=Path("/s/chapter-002.md"),
            ),
        ]
        report = asyncio.run(
            run_analyze_pipeline(
                chapters,
                cfg=GhostCopyeditorConfig(),
                manuscript_path="/s",
                manuscript_name="s",
                story_slug="s",
            )
        )
        ids = [f.id for f in report.findings]
        assert len(ids) == len(set(ids))
        assert any(i.startswith("det-c001-") for i in ids)
        assert any(i.startswith("det-c002-") for i in ids)
