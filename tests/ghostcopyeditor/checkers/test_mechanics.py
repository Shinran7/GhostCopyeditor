"""Tests for mechanics checkers (ship + report-only)."""

from __future__ import annotations

from pathlib import Path

from ghostcopyeditor.checkers.mechanics import MechanicsChecker
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter


def _chapter(text: str, *, num: int = 1) -> Chapter:
    return Chapter(
        title="T",
        content=text,
        chapter_number=num,
        source_path=Path(f"/story/chapters/chapter-{num:03d}.md"),
    )


def _rules(text: str) -> list:
    return MechanicsChecker().check(_chapter(text), GhostCopyeditorConfig())


class TestDoubleSpace:
    def test_collapses_mid_line(self) -> None:
        findings = _rules("He  walked.\n")
        hits = [f for f in findings if f.rule_id == "mech.double_space"]
        assert len(hits) == 1
        assert hits[0].applyable is True
        assert hits[0].replacement == " "
        assert hits[0].metadata["expected_old"] == "  "

    def test_skips_leading_indent(self) -> None:
        findings = _rules("  indented\n")
        assert not [f for f in findings if f.rule_id == "mech.double_space"]

    def test_skips_frontmatter_and_fences(self) -> None:
        text = "---\ntitle:  x\n---\n\n```\ncode  here\n```\n\nOk  prose.\n"
        findings = _rules(text)
        hits = [f for f in findings if f.rule_id == "mech.double_space"]
        assert len(hits) == 1
        assert "Ok" in text[hits[0].location.char_start - 2 : hits[0].location.char_end + 6]


class TestTrailingWs:
    def test_strips_line_end(self) -> None:
        findings = _rules("Hello  \nWorld\n")
        hits = [f for f in findings if f.rule_id == "mech.trailing_ws"]
        assert len(hits) == 1
        assert hits[0].replacement == ""
        assert hits[0].applyable is True


class TestSpaceBeforePunct:
    def test_fixes_outside_quotes(self) -> None:
        findings = _rules("Hello , world.\n")
        hits = [f for f in findings if f.rule_id == "mech.space_before_punct"]
        assert len(hits) == 1
        assert hits[0].replacement == ","
        assert hits[0].metadata["expected_old"] == " ,"

    def test_skips_inside_dialogue_quotes(self) -> None:
        # Fiction dialogue: do not "fix" spacing inside quotes.
        findings = _rules('He said, "Wait , please."\n')
        hits = [f for f in findings if f.rule_id == "mech.space_before_punct"]
        assert hits == []

    def test_unmatched_quotes_do_not_auto_insert(self) -> None:
        findings = _rules('He said "Wait , please.\n')
        # Unmatched opener → no quote span → still flags outside (known limit).
        hits = [f for f in findings if f.rule_id == "mech.space_before_punct"]
        assert len(hits) == 1


class TestRepeatedPunct:
    def test_report_only(self) -> None:
        findings = _rules("No!!!! What????\n")
        hits = [f for f in findings if f.rule_id == "mech.repeated_punct"]
        assert len(hits) == 2
        assert all(not f.applyable for f in hits)
