"""Light local echo heuristics (report-only)."""

from __future__ import annotations

import re
from collections import deque
from typing import ClassVar

from ghostcopyeditor.checkers.regions import non_prose_spans, span_overlaps_any
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Severity,
    location_from_span,
)

_WORD_RE = re.compile(r"[A-Za-z']+")
_PARA_BREAK = re.compile(r"\n\s*\n")

_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "but",
        "or",
        "is",
        "was",
        "were",
        "are",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "must",
        "can",
        "could",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "out",
        "off",
        "over",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "because",
        "about",
        "up",
        "it",
        "its",
        "he",
        "she",
        "they",
        "them",
        "his",
        "her",
        "their",
        "him",
        "my",
        "your",
        "we",
        "me",
        "i",
        "you",
        "that",
        "this",
        "those",
        "these",
        "what",
        "which",
        "who",
        "whom",
        "if",
        "while",
        "until",
        "also",
        "still",
        "even",
        "back",
        "said",
        "says",
        "am",
        "yet",
        "against",
        "down",
        "away",
        "our",
        "whose",
        "now",
    }
)


def _sentence_span(content: str, start: int, end: int) -> tuple[int, int]:
    """Return the sentence (or line) that contains the half-open span."""
    left = -1
    for index in range(start - 1, -1, -1):
        if content[index] in ".!?\n":
            left = index
            break
    right = len(content)
    for index in range(end, len(content)):
        if content[index] == "\n":
            right = index
            break
        if content[index] in ".!?":
            right = index + 1
            break
    sent_start = left + 1
    while sent_start < right and content[sent_start] in " \t":
        sent_start += 1
    return sent_start, right


def _paragraph_spans(content: str) -> list[tuple[int, int]]:
    """Half-open paragraph spans split on blank lines."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    for match in _PARA_BREAK.finditer(content):
        start, end = cursor, match.start()
        if start < end and content[start:end].strip():
            spans.append((start, end))
        cursor = match.end()
    if cursor < len(content) and content[cursor:].strip():
        spans.append((cursor, len(content)))
    return spans


def _phrase_has_substance(gram: tuple[str, ...]) -> bool:
    return any(word not in _STOP and len(word) > 2 for word in gram)


def _find_phrase_dup_in_tokens(
    tokens: list[tuple[str, int, int]],
    *,
    min_n: int,
    max_n: int,
    max_gap: int,
) -> tuple[str, int, int, int] | None:
    """Return (phrase, char_start, char_end, gap) for the best close-proximity hit."""
    if len(tokens) < min_n * 2:
        return None
    words = [word for word, _, _ in tokens]
    best_phrase = ""
    best_len = 0
    best_gap = max_gap + 1
    best_span: tuple[int, int] | None = None

    for n in range(max_n, min_n - 1, -1):
        positions: dict[tuple[str, ...], list[int]] = {}
        for i in range(len(words) - n + 1):
            gram = tuple(words[i : i + n])
            positions.setdefault(gram, []).append(i)

        for gram, starts in positions.items():
            if len(starts) < 2 or not _phrase_has_substance(gram):
                continue
            phrase = " ".join(gram)
            for j in range(len(starts) - 1):
                gap = starts[j + 1] - (starts[j] + n)
                if gap > max_gap:
                    continue
                if n > best_len or (n == best_len and gap < best_gap):
                    first = starts[j]
                    second = starts[j + 1]
                    best_phrase = phrase
                    best_len = n
                    best_gap = gap
                    best_span = (tokens[first][1], tokens[second + n - 1][2])

    if best_span is None:
        return None
    return best_phrase, best_span[0], best_span[1], best_gap


class EchoChecker:
    """Flag local word echo and close-proximity phrase stutter."""

    rule_ids: ClassVar[tuple[str, ...]] = (
        "echo.local_repeat",
        "echo.phrase_dup",
    )

    def check(self, chapter: Chapter, cfg: GhostCopyeditorConfig) -> list[Finding]:
        content = chapter.content
        skipped = non_prose_spans(content)
        findings = self._check_local_repeat(chapter, cfg, skipped)
        findings.extend(self._check_phrase_dup(chapter, cfg, skipped))
        return findings

    def _check_local_repeat(
        self,
        chapter: Chapter,
        cfg: GhostCopyeditorConfig,
        skipped: list,
    ) -> list[Finding]:
        content = chapter.content
        window = max(1, cfg.echo_window_words)
        min_repeats = max(2, cfg.echo_min_repeats)

        tokens: list[tuple[str, int, int]] = []
        for match in _WORD_RE.finditer(content):
            start, end = match.start(), match.end()
            if span_overlaps_any(start, end, skipped):
                continue
            word = match.group(0).lower()
            if word in _STOP or len(word) < 3:
                continue
            tokens.append((word, start, end))

        findings: list[Finding] = []
        seen_words: set[str] = set()
        # Sliding window over content-word tokens. One note per word cluster.
        ring: deque[tuple[str, int, int]] = deque()
        counts: dict[str, int] = {}
        for token in tokens:
            word, start, end = token
            ring.append(token)
            counts[word] = counts.get(word, 0) + 1
            while len(ring) > window:
                old_word, _, _ = ring.popleft()
                counts[old_word] -= 1
                if counts[old_word] <= 0:
                    del counts[old_word]
                    seen_words.discard(old_word)
            if counts.get(word, 0) >= min_repeats and word not in seen_words:
                seen_words.add(word)
                sent_start, sent_end = _sentence_span(content, start, end)
                sentence = content[sent_start:sent_end].strip()
                findings.append(
                    Finding(
                        id="",
                        category=Category.ECHO,
                        severity=Severity.SUGGESTION,
                        message=(
                            f"Word '{word}' repeats {counts[word]} times "
                            f"within {window} content words."
                        ),
                        location=location_from_span(
                            chapter, sent_start, sent_end, excerpt=sentence
                        ),
                        engine=Engine.DETERMINISTIC,
                        suggestion=None,
                        rule_id="echo.local_repeat",
                        applyable=False,
                        replacement=None,
                        metadata={
                            "word": word,
                            "repeat_count": counts[word],
                            "window": window,
                        },
                    )
                )
        return findings

    def _check_phrase_dup(
        self,
        chapter: Chapter,
        cfg: GhostCopyeditorConfig,
        skipped: list,
    ) -> list[Finding]:
        """Close-proximity 3–4 word stutter (Autonomicon polish-pass signature)."""
        content = chapter.content
        min_n = max(2, cfg.echo_phrase_min_n)
        max_n = max(min_n, cfg.echo_phrase_max_n)
        max_gap = max(0, cfg.echo_phrase_max_gap)
        findings: list[Finding] = []

        for para_start, para_end in _paragraph_spans(content):
            tokens: list[tuple[str, int, int]] = []
            for match in _WORD_RE.finditer(content, para_start, para_end):
                start, end = match.start(), match.end()
                if span_overlaps_any(start, end, skipped):
                    continue
                tokens.append((match.group(0).lower(), start, end))

            hit = _find_phrase_dup_in_tokens(
                tokens, min_n=min_n, max_n=max_n, max_gap=max_gap
            )
            if hit is None:
                continue
            phrase, start, end, gap = hit
            excerpt = content[para_start:para_end].strip()
            findings.append(
                Finding(
                    id="",
                    category=Category.ECHO,
                    severity=Severity.SUGGESTION,
                    message=(
                        f"Phrase '{phrase}' appears twice in close proximity "
                        f"within the same paragraph — likely a polish-pass stutter."
                    ),
                    location=location_from_span(
                        chapter, start, end, excerpt=excerpt
                    ),
                    engine=Engine.DETERMINISTIC,
                    suggestion=None,
                    rule_id="echo.phrase_dup",
                    applyable=False,
                    replacement=None,
                    metadata={
                        "phrase": phrase,
                        "gap": gap,
                        "min_n": min_n,
                        "max_n": max_n,
                        "max_gap": max_gap,
                    },
                )
            )
        return findings


__all__ = ["EchoChecker"]
