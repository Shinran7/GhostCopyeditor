"""Tests for non-prose region helpers."""

from __future__ import annotations

from ghostcopyeditor.checkers.regions import (
    Span,
    find_double_quote_spans,
    find_frontmatter_span,
    in_dialogue_quotes,
    non_prose_spans,
    span_covered_by,
    span_overlaps_any,
)


def test_frontmatter_and_fence_regions() -> None:
    text = "---\ntitle: x\n---\n\n# Hi\n\n```\ncode\n```\n\nProse.\n\n---\n\nMore.\n"
    spans = non_prose_spans(text)
    assert find_frontmatter_span(text) is not None
    assert any(s.start == 0 for s in spans)
    assert span_overlaps_any(text.index("code"), text.index("code") + 4, spans)


def test_quote_spans_and_unmatched() -> None:
    paired = 'He said, "Hello."\n'
    spans = find_double_quote_spans(paired)
    assert len(spans) == 1
    assert in_dialogue_quotes(paired.index("Hello"), paired)

    unmatched = 'He said, "Hello.\n'
    assert find_double_quote_spans(unmatched) == []


def test_span_helpers() -> None:
    s = Span(2, 5)
    assert s.contains(2)
    assert not s.contains(5)
    assert s.covers(2, 4)
    assert span_covered_by(2, 4, [s])
    assert s.overlaps(Span(4, 8))
