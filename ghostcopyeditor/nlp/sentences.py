"""Prose sentences with scene numbers (spaCy when available, else a simple split).

Offsets index the full chapter text. Each paragraph is parsed on its own, so
a sentence never runs across a blank line or a ``---`` scene break.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ghostcopyeditor.checkers.regions import (
    non_prose_spans,
    scene_number_at,
    scene_spans,
)
from ghostcopyeditor.nlp.spacy_runtime import get_nlp

_PARA_RE = re.compile(r"[^\n](?:.|\n(?![ \t\r]*\n))*")
_FALLBACK_SPLIT_RE = re.compile(r"(?<=[.!?])[\"”’)]*\s+")
_QUOTE_CHARS = frozenset('"“”')


@dataclass(frozen=True)
class Sentence:
    """One prose sentence. ``end`` is exclusive."""

    start: int
    end: int
    scene: int
    dialogue: bool
    text: str
    span: Any = None  # spaCy Span when parsed; None on the fallback path


def _prose_segments(text: str) -> list[tuple[int, int]]:
    """Text outside frontmatter, code, headings, and scene breaks."""
    segments: list[tuple[int, int]] = []
    cursor = 0
    for span in non_prose_spans(text):
        if span.start > cursor:
            segments.append((cursor, span.start))
        cursor = max(cursor, span.end)
    if cursor < len(text):
        segments.append((cursor, len(text)))
    return segments


def _paragraphs(text: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for seg_start, seg_end in _prose_segments(text):
        for match in _PARA_RE.finditer(text, seg_start, seg_end):
            start, end = match.start(), match.end()
            if text[start:end].strip():
                out.append((start, end))
    return out


def _fallback_spans(chunk: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = 0
    for match in _FALLBACK_SPLIT_RE.finditer(chunk):
        spans.append((cursor, match.start() + len(match.group(0).rstrip())))
        cursor = match.end()
    if cursor < len(chunk):
        spans.append((cursor, len(chunk)))
    return spans


def _is_dialogue(text: str) -> bool:
    return any(ch in _QUOTE_CHARS for ch in text)


@lru_cache(maxsize=8)
def _sentences_cached(text: str, use_nlp: bool) -> tuple[Sentence, ...]:
    scenes = scene_spans(text)
    paras = _paragraphs(text)
    nlp = get_nlp() if use_nlp else None
    out: list[Sentence] = []
    docs: list[Any] = (
        list(nlp.pipe([text[s:e] for s, e in paras])) if nlp is not None else []
    )
    for i, (p_start, p_end) in enumerate(paras):
        chunk = text[p_start:p_end]
        if docs:
            pieces = [(int(s.start_char), int(s.end_char), s) for s in docs[i].sents]
        else:
            pieces = [(s, e, None) for s, e in _fallback_spans(chunk)]
        for s, e, span in pieces:
            raw = chunk[s:e]
            stripped = raw.strip()
            if not stripped:
                continue
            lead = len(raw) - len(raw.lstrip())
            start = p_start + s + lead
            end = start + len(stripped)
            out.append(
                Sentence(
                    start=start,
                    end=end,
                    scene=scene_number_at(start, scenes) or 1,
                    dialogue=_is_dialogue(stripped),
                    text=stripped,
                    span=span,
                )
            )
    return tuple(out)


def prose_sentences(text: str, *, use_nlp: bool = True) -> list[Sentence]:
    """All prose sentences in *text*, in order."""
    return list(_sentences_cached(text, use_nlp))


def sentence_index_at(sentences: list[Sentence], index: int) -> int | None:
    """Index into *sentences* of the sentence holding char *index*, else None."""
    starts = [s.start for s in sentences]
    i = bisect.bisect_right(starts, index) - 1
    if i >= 0 and sentences[i].start <= index < sentences[i].end:
        return i
    return None


def clear_cache() -> None:
    """Drop cached parses (tests, long runs)."""
    _sentences_cached.cache_clear()


__all__ = [
    "Sentence",
    "clear_cache",
    "prose_sentences",
    "sentence_index_at",
]
