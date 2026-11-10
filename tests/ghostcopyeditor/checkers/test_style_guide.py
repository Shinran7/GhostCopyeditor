"""Tests for the per-book style guide checker."""

from __future__ import annotations

from pathlib import Path

from ghostcopyeditor.checkers.apply import apply_to_content
from ghostcopyeditor.checkers.style_guide import StyleGuideChecker, _match_case
from ghostcopyeditor.config import GhostCopyeditorConfig, StyleGuide
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import Severity

TEXT = (
    "# Grey Heading\n\n"
    "She waited a beat. Grey light, grey walls, GREY sky.\n"
    "Suddenly it rained. Suddenly it stopped. Suddenly   it began.\n"
    "He let out a\nbreath. The gray cat slept.\n"
)


def _check(**guide: object) -> list:
    ch = Chapter(title="t", content=TEXT, chapter_number=1, source_path=Path("c.md"))
    cfg = GhostCopyeditorConfig(style_guide=StyleGuide(**guide))
    return StyleGuideChecker().check(ch, cfg)


def test_empty_guide() -> None:
    assert _check() == []


def test_banned_spans_lines() -> None:
    findings = _check(banned=["a beat", "let out a breath", "  "])
    assert [f.location.excerpt for f in findings] == ["a beat", "let out a\nbreath"]
    assert all(f.severity == Severity.WARNING for f in findings)
    assert not any(f.applyable for f in findings)


def test_pet_words_over_limit() -> None:
    assert _check(pet_words={"suddenly": 3}) == []
    findings = _check(pet_words={"suddenly": 2})
    assert len(findings) == 3
    assert findings[0].metadata["count"] == 3


def test_spellings_apply_and_keep_case() -> None:
    findings = _check(spellings={"grey": "gray", "gray": "gray"})
    assert [f.replacement for f in findings] == ["Gray", "gray", "GRAY"]
    assert all(f.applyable for f in findings)
    fixed = apply_to_content(TEXT, findings)
    fixed_text = fixed[0] if isinstance(fixed, tuple) else fixed
    assert "Gray light, gray walls, GRAY sky" in fixed_text
    assert "# Grey Heading" in fixed_text  # headings skipped


def test_match_case() -> None:
    assert _match_case("A", "b") == "B"
    assert _match_case("x", "y") == "y"
