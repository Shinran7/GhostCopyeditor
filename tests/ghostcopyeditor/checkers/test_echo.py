"""Tests for local echo heuristic."""

from __future__ import annotations

from pathlib import Path

from ghostcopyeditor.checkers.echo import EchoChecker
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter


def _chapter(text: str) -> Chapter:
    return Chapter(
        title="T",
        content=text,
        chapter_number=1,
        source_path=Path("/story/chapters/chapter-001.md"),
    )


class TestEcho:
    def test_flags_local_repeat(self) -> None:
        # "shadow" thrice inside a short window.
        text = (
            "The shadow moved. Another shadow waited. "
            "A third shadow rose near the wall.\n"
        )
        cfg = GhostCopyeditorConfig(echo_window_words=40, echo_min_repeats=3)
        findings = EchoChecker().check(_chapter(text), cfg)
        hits = [f for f in findings if f.rule_id == "echo.local_repeat"]
        assert len(hits) == 1
        assert hits[0].metadata["word"] == "shadow"
        assert "shadow" in hits[0].location.excerpt.lower()
        assert len(hits[0].location.excerpt) > len("shadow")
        assert all(not f.applyable for f in hits)

    def test_one_note_when_the_count_ticks_and_case_changes(self) -> None:
        text = "Near the gate. near the wall. Near the road. near the well.\n"
        cfg = GhostCopyeditorConfig(echo_window_words=40, echo_min_repeats=3)
        findings = EchoChecker().check(_chapter(text), cfg)
        assert len(findings) == 1
        assert findings[0].metadata["word"] == "near"


def test_echo_stays_out_of_the_action_list() -> None:
    from ghostcopyeditor.models.finding import Category, Engine, Finding, Location, Severity
    from ghostcopyeditor.models.report import partition_action_list

    echo = Finding(
        id="det-c001-0001",
        category=Category.ECHO,
        severity=Severity.SUGGESTION,
        message="Word 'one' repeats.",
        location=Location(chapter_number=1, chapter_path="chapter-001.md", excerpt="one one one"),
        engine=Engine.DETERMINISTIC,
        rule_id="echo.local_repeat",
    )
    edit = Finding(
        id="llm-c001-0001",
        category=Category.GARBLED,
        severity=Severity.ERROR,
        message="Dropped letter.",
        location=Location(chapter_number=1, chapter_path="chapter-001.md", excerpt="It stanchions"),
        engine=Engine.LLM,
        rule_id="llm.garbled",
        applyable=True,
        replacement="Its stanchions",
    )
    action, may_look = partition_action_list([echo, edit])
    assert action == [edit]
    assert may_look == [echo]

    def test_below_threshold_silent(self) -> None:
        text = "The shadow moved. Another figure waited.\n"
        cfg = GhostCopyeditorConfig(echo_window_words=40, echo_min_repeats=3)
        findings = EchoChecker().check(_chapter(text), cfg)
        assert findings == []
