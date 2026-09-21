"""Light local echo heuristic (report-only)."""

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
    }
)


class EchoChecker:
    """Flag the same content word repeating ≥ N times inside a sliding window."""

    rule_ids: ClassVar[tuple[str, ...]] = ("echo.local_repeat",)

    def check(self, chapter: Chapter, cfg: GhostCopyeditorConfig) -> list[Finding]:
        content = chapter.content
        skipped = non_prose_spans(content)
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
        seen_spans: set[tuple[int, int]] = set()
        # Sliding window over content-word tokens.
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
            if counts.get(word, 0) >= min_repeats:
                key = (start, end)
                if key in seen_spans:
                    continue
                seen_spans.add(key)
                excerpt = content[start:end]
                findings.append(
                    Finding(
                        id="",
                        category=Category.ECHO,
                        severity=Severity.SUGGESTION,
                        message=(
                            f"Word '{excerpt}' repeats {counts[word]} times "
                            f"within {window} content words."
                        ),
                        location=location_from_span(
                            chapter, start, end, excerpt=excerpt
                        ),
                        engine=Engine.DETERMINISTIC,
                        suggestion=None,
                        rule_id="echo.local_repeat",
                        applyable=False,
                        replacement=None,
                        metadata={"repeat_count": counts[word], "window": window},
                    )
                )
        return findings


__all__ = ["EchoChecker"]
