"""Tests for style checkers (report-only)."""

from __future__ import annotations

from pathlib import Path

from ghostcopyeditor.checkers.style import StyleChecker
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter


def _chapter(text: str) -> Chapter:
    return Chapter(
        title="T",
        content=text,
        chapter_number=1,
        source_path=Path("/story/chapters/chapter-001.md"),
    )


class TestEmDash:
    def test_flags_unicode_and_double_hyphen(self) -> None:
        text = "Wait—no. Wait -- no.\n"
        findings = StyleChecker().check(_chapter(text), GhostCopyeditorConfig())
        hits = [f for f in findings if f.rule_id == "style.em_dash"]
        assert len(hits) == 2
        assert all(not f.applyable for f in hits)

    def test_ignores_epigraph_credit_in_header(self) -> None:
        text = (
            "\ufeff---\n"
            "title: Salt\n"
            'epigraph_attribution: "— Hestor Quill, price-list preamble"\n'
            "---\n\n"
            "The salt was white.\n"
        )
        findings = StyleChecker().check(_chapter(text), GhostCopyeditorConfig())
        assert findings == []

    def test_skips_scene_break_triple_hyphen(self) -> None:
        text = "Before.\n\n---\n\nAfter.\n"
        findings = StyleChecker().check(_chapter(text), GhostCopyeditorConfig())
        assert findings == []
