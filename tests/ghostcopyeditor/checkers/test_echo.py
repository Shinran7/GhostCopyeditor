"""Tests for local echo heuristics."""

from __future__ import annotations

from pathlib import Path

from ghostcopyeditor.checkers.echo import EchoChecker
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import Category, Engine, Finding, Location, Severity
from ghostcopyeditor.models.report import partition_action_list


def _chapter(text: str) -> Chapter:
    return Chapter(
        title="T",
        content=text,
        chapter_number=1,
        source_path=Path("/story/chapters/chapter-001.md"),
    )


class TestEchoLocalRepeat:
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
        local = [f for f in findings if f.rule_id == "echo.local_repeat"]
        assert len(local) == 1
        assert local[0].metadata["word"] == "near"

    def test_below_threshold_silent(self) -> None:
        text = "The shadow moved. Another figure waited.\n"
        cfg = GhostCopyeditorConfig(echo_window_words=40, echo_min_repeats=3)
        findings = EchoChecker().check(_chapter(text), cfg)
        assert findings == []


class TestEchoPhraseDup:
    def test_flags_close_proximity_phrase_stutter(self) -> None:
        text = (
            "The auditor stepped back without complaint, which measured the "
            "morning... No. Which measured the air. Garen knelt.\n"
        )
        findings = EchoChecker().check(_chapter(text), GhostCopyeditorConfig())
        hits = [f for f in findings if f.rule_id == "echo.phrase_dup"]
        assert len(hits) == 1
        assert hits[0].metadata["phrase"] == "which measured the"
        assert hits[0].severity == Severity.SUGGESTION
        assert hits[0].applyable is False
        assert "which measured the" in hits[0].location.excerpt.lower()

    def test_prefers_longest_matched_phrase(self) -> None:
        para = (
            "cold dark stone hall then cold dark stone hall "
            "and later dark stone hall dark stone hall remain\n"
        )
        findings = EchoChecker().check(_chapter(para), GhostCopyeditorConfig())
        hits = [f for f in findings if f.rule_id == "echo.phrase_dup"]
        assert len(hits) == 1
        assert hits[0].metadata["phrase"] == "cold dark stone hall"

    def test_one_hit_per_paragraph(self) -> None:
        text = (
            "Nobody inherits your debt and nobody inherits your bargain.\n\n"
            "I'm not asking to go faster. I'm asking to go pointed.\n"
        )
        findings = EchoChecker().check(_chapter(text), GhostCopyeditorConfig())
        hits = [f for f in findings if f.rule_id == "echo.phrase_dup"]
        assert len(hits) == 2
        phrases = {f.metadata["phrase"] for f in hits}
        assert "nobody inherits your" in phrases
        assert "asking to go" in phrases

    def test_gap_beyond_max_is_silent(self) -> None:
        # Parallel clauses with a wider gap should not trip max_gap=2.
        text = (
            "The wood had not changed. The rent clause had not changed.\n"
        )
        findings = EchoChecker().check(_chapter(text), GhostCopyeditorConfig())
        assert [f for f in findings if f.rule_id == "echo.phrase_dup"] == []

    def test_skips_non_prose_regions(self) -> None:
        text = (
            "```\n"
            "which measured the dial which measured the dial\n"
            "```\n"
            "He walked on without a second thought.\n"
        )
        findings = EchoChecker().check(_chapter(text), GhostCopyeditorConfig())
        assert [f for f in findings if f.rule_id == "echo.phrase_dup"] == []


def test_echo_stays_out_of_the_action_list() -> None:
    echo = Finding(
        id="det-c001-0001",
        category=Category.ECHO,
        severity=Severity.SUGGESTION,
        message="Word 'one' repeats.",
        location=Location(
            chapter_number=1, chapter_path="chapter-001.md", excerpt="one one one"
        ),
        engine=Engine.DETERMINISTIC,
        rule_id="echo.local_repeat",
    )
    phrase = Finding(
        id="det-c001-0002",
        category=Category.ECHO,
        severity=Severity.SUGGESTION,
        message="Phrase stutter.",
        location=Location(
            chapter_number=1,
            chapter_path="chapter-001.md",
            excerpt="which measured the morning which measured the air",
        ),
        engine=Engine.DETERMINISTIC,
        rule_id="echo.phrase_dup",
    )
    edit = Finding(
        id="llm-c001-0001",
        category=Category.GARBLED,
        severity=Severity.ERROR,
        message="Dropped letter.",
        location=Location(
            chapter_number=1, chapter_path="chapter-001.md", excerpt="It stanchions"
        ),
        engine=Engine.LLM,
        rule_id="llm.garbled",
        applyable=True,
        replacement="Its stanchions",
    )
    action, may_look = partition_action_list([echo, phrase, edit])
    assert action == [edit]
    assert may_look == [echo, phrase]
