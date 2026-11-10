"""Tests for scene/sentence annotation on findings."""

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
    location_from_span,
)
from ghostcopyeditor.nlp.sentences import clear_cache
from ghostcopyeditor.pipeline.positions import annotate_positions, scene_profiles

TEXT = (
    "---\ntitle: x\n---\n\n"
    "She walked in. He sat down.\n\n"
    "# Heading\n\n"
    '"Hello there," she said. The door shut.\n\n'
    "---\n\n"
    "Rain fell all night.\r\n\r\nMorning came late.\n"
)


@pytest.fixture(autouse=True)
def _fresh() -> None:
    clear_cache()
    yield
    clear_cache()


def _chapter(text: str) -> Chapter:
    return Chapter(title="t", content=text, chapter_number=1, source_path=Path("c.md"))


def _finding(chapter: Chapter, start: int, end: int) -> Finding:
    return Finding(
        id="x",
        category=Category.STYLE,
        severity=Severity.INFO,
        message="m",
        location=location_from_span(chapter, start, end),
        engine=Engine.DETERMINISTIC,
    )


class TestPositions:
    def test_annotate_scene_and_sentence(self) -> None:
        ch = _chapter(TEXT)
        start = TEXT.index("sat down")
        rain = TEXT.index("Rain")
        f1 = _finding(ch, start, start + 3)
        f2 = _finding(ch, TEXT.index("walked"), rain + 4)
        nowhere = Finding(
            id="y",
            category=Category.STYLE,
            severity=Severity.INFO,
            message="m",
            location=Location(chapter_number=1, chapter_path="c.md"),
            engine=Engine.DETERMINISTIC,
        )
        gap = TEXT.index("# Heading")
        f3 = _finding(ch, gap, gap + 2)
        out = annotate_positions([f1, f2, nowhere, f3], ch)
        assert out[0].location.scene == 1
        loc = out[0].location
        assert TEXT[loc.sentence_start : loc.sentence_end] == "He sat down."
        assert out[1].location.sentence_end == TEXT.index("Rain fell all night.") + len(
            "Rain fell all night."
        )
        assert out[2].location.scene is None
        assert out[3].location.sentence_start is None

    def test_end_outside_sentence_uses_first(self) -> None:
        ch = _chapter(TEXT)
        start = TEXT.index("The door shut.")
        f = _finding(ch, start, TEXT.index("Rain") - 2)
        out = annotate_positions([f], ch)
        assert out[0].location.sentence_end == start + len("The door shut.")

    def test_scene_profiles(self) -> None:
        profiles = scene_profiles(_chapter(TEXT))
        assert [p["scene"] for p in profiles] == [1, 2]
        assert profiles[1]["sentences"] == 2
        assert profiles[1]["words"] == 7
        assert profiles[0]["narration_sentences"] < profiles[0]["sentences"]
