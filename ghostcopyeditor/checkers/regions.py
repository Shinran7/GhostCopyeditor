"""Non-prose region and dialogue-quote helpers for deterministic checkers.

Offsets always index into the full chapter ``content`` string. Checkers skip
matching inside frontmatter, fenced code, and (for some rules) dialogue quotes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    start: int
    end: int  # exclusive

    def contains(self, index: int) -> bool:
        return self.start <= index < self.end

    def overlaps(self, other: Span) -> bool:
        return self.start < other.end and other.start < self.end

    def covers(self, start: int, end: int) -> bool:
        return self.start <= start and end <= self.end


# Optional BOM. Chapter files from Autonomicon often start with one, and the
# epigraph credit ("— Hestor Quill") lives inside that header.
_FRONTMATTER_RE = re.compile(r"\A\ufeff?---\r?\n.*?\r?\n---\r?\n?", re.DOTALL)
_FENCE_RE = re.compile(r"^```[^\n]*\n.*?^```[ \t]*\r?\n?", re.MULTILINE | re.DOTALL)
_HEADING_RE = re.compile(r"^#{1,6}[ \t]+.*$", re.MULTILINE)
_SCENE_BREAK_RE = re.compile(r"^---[ \t]*$", re.MULTILINE)


def find_frontmatter_span(content: str) -> Span | None:
    match = _FRONTMATTER_RE.match(content)
    if match is None:
        return None
    return Span(match.start(), match.end())


def find_code_fence_spans(content: str) -> list[Span]:
    return [Span(m.start(), m.end()) for m in _FENCE_RE.finditer(content)]


def find_heading_spans(content: str) -> list[Span]:
    return [Span(m.start(), m.end()) for m in _HEADING_RE.finditer(content)]


def find_scene_break_spans(content: str) -> list[Span]:
    return [Span(m.start(), m.end()) for m in _SCENE_BREAK_RE.finditer(content)]


def non_prose_spans(content: str) -> list[Span]:
    """Frontmatter, fenced code, headings, and ``---`` scene breaks."""
    spans: list[Span] = []
    fm = find_frontmatter_span(content)
    if fm is not None:
        spans.append(fm)
    spans.extend(find_code_fence_spans(content))
    spans.extend(find_heading_spans(content))
    spans.extend(find_scene_break_spans(content))
    return _merge_spans(spans)


def in_any_span(index: int, spans: list[Span]) -> bool:
    return any(s.contains(index) for s in spans)


def span_covered_by(start: int, end: int, spans: list[Span]) -> bool:
    return any(s.covers(start, end) for s in spans)


def span_overlaps_any(start: int, end: int, spans: list[Span]) -> bool:
    probe = Span(start, end)
    return any(s.overlaps(probe) for s in spans)


def find_double_quote_spans(content: str) -> list[Span]:
    """Paired ASCII double-quote spans. Unmatched opener is ignored (no auto-fix)."""
    spans: list[Span] = []
    i = 0
    n = len(content)
    while i < n:
        if content[i] != '"':
            i += 1
            continue
        j = i + 1
        while j < n and content[j] != '"':
            j += 1
        if j >= n:
            break
        spans.append(Span(i, j + 1))
        i = j + 1
    return spans


def in_dialogue_quotes(index: int, content: str, quote_spans: list[Span] | None = None) -> bool:
    spans = quote_spans if quote_spans is not None else find_double_quote_spans(content)
    return in_any_span(index, spans)


def _merge_spans(spans: list[Span]) -> list[Span]:
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: (s.start, s.end))
    merged: list[Span] = [ordered[0]]
    for span in ordered[1:]:
        last = merged[-1]
        if span.start <= last.end:
            merged[-1] = Span(last.start, max(last.end, span.end))
        else:
            merged.append(span)
    return merged


__all__ = [
    "Span",
    "find_code_fence_spans",
    "find_double_quote_spans",
    "find_frontmatter_span",
    "find_heading_spans",
    "find_scene_break_spans",
    "in_any_span",
    "in_dialogue_quotes",
    "non_prose_spans",
    "span_covered_by",
    "span_overlaps_any",
]
