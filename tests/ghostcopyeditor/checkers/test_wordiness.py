"""Tests for wordiness phrase map."""

from __future__ import annotations

from pathlib import Path

from ghostcopyeditor.checkers.wordiness import WordinessChecker
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter


def _chapter(text: str) -> Chapter:
    return Chapter(
        title="T",
        content=text,
        chapter_number=1,
        source_path=Path("/story/chapters/chapter-001.md"),
    )


class TestWordiness:
    def test_in_order_to(self) -> None:
        findings = WordinessChecker().check(
            _chapter("She left in order to rest.\n"),
            GhostCopyeditorConfig(),
        )
        hits = [f for f in findings if f.rule_id == "word.in_order_to"]
        assert len(hits) == 1
        assert hits[0].replacement == "to"
        assert hits[0].applyable is True
        assert hits[0].metadata["expected_old"].lower() == "in order to"

    def test_due_to_the_fact(self) -> None:
        findings = WordinessChecker().check(
            _chapter("He stayed due to the fact that rain fell.\n"),
            GhostCopyeditorConfig(),
        )
        hits = [f for f in findings if f.rule_id == "word.due_to_the_fact"]
        assert len(hits) == 1
        assert hits[0].replacement == "because"

    def test_small_map_and_case(self) -> None:
        findings = WordinessChecker().check(
            _chapter("Prior to dawn, a number of birds sang.\n"),
            GhostCopyeditorConfig(),
        )
        by_rule = {f.rule_id for f in findings}
        assert "word.small_map" in by_rule
        prior = next(f for f in findings if f.location.excerpt.lower() == "prior to")
        assert prior.replacement == "Before"

    def test_skips_inside_quotes(self) -> None:
        findings = WordinessChecker().check(
            _chapter('He said, "I left in order to rest."\n'),
            GhostCopyeditorConfig(),
        )
        assert findings == []

    def test_disabled_by_config(self) -> None:
        cfg = GhostCopyeditorConfig(wordiness_enabled=False)
        findings = WordinessChecker().check(
            _chapter("She left in order to rest.\n"), cfg
        )
        assert findings == []
