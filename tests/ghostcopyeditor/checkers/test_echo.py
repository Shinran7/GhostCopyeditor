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
        assert hits
        assert all(not f.applyable for f in hits)
        assert any("shadow" in f.location.excerpt.lower() for f in hits)

    def test_below_threshold_silent(self) -> None:
        text = "The shadow moved. Another figure waited.\n"
        cfg = GhostCopyeditorConfig(echo_window_words=40, echo_min_repeats=3)
        findings = EchoChecker().check(_chapter(text), cfg)
        assert findings == []
