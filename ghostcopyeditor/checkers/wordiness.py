"""Conservative wordiness phrase map (applyable outside quotes)."""

from __future__ import annotations

import re
from typing import ClassVar

from ghostcopyeditor.checkers.regions import (
    find_double_quote_spans,
    in_any_span,
    non_prose_spans,
    span_overlaps_any,
)
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Severity,
    location_from_span,
)

# (phrase, replacement, rule_id). Case-insensitive match; replacement keeps
# lowercase unless the source starts with an uppercase letter.
_PHRASES: tuple[tuple[str, str, str], ...] = (
    ("in order to", "to", "word.in_order_to"),
    ("due to the fact that", "because", "word.due_to_the_fact"),
    ("due to the fact", "because", "word.due_to_the_fact"),
    ("a large number of", "many", "word.small_map"),
    ("a number of", "several", "word.small_map"),
    ("at this point in time", "now", "word.small_map"),
    ("in spite of the fact that", "although", "word.small_map"),
    ("for the purpose of", "to", "word.small_map"),
    ("in the event that", "if", "word.small_map"),
    ("with regard to", "about", "word.small_map"),
    ("in light of the fact that", "because", "word.small_map"),
    ("it is important to note that", "", "word.small_map"),
    ("make a decision", "decide", "word.small_map"),
    ("take into consideration", "consider", "word.small_map"),
    ("has the ability to", "can", "word.small_map"),
    ("prior to", "before", "word.small_map"),
    ("subsequent to", "after", "word.small_map"),
    ("in close proximity to", "near", "word.small_map"),
)


def _compile_phrases() -> list[tuple[re.Pattern[str], str, str]]:
    compiled: list[tuple[re.Pattern[str], str, str]] = []
    for phrase, replacement, rule_id in _PHRASES:
        pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
        compiled.append((pattern, replacement, rule_id))
    return compiled


_COMPILED = _compile_phrases()


class WordinessChecker:
    """Tiny curated phrase map. No synonymizer."""

    rule_ids: ClassVar[tuple[str, ...]] = (
        "word.in_order_to",
        "word.due_to_the_fact",
        "word.small_map",
    )

    def check(self, chapter: Chapter, cfg: GhostCopyeditorConfig) -> list[Finding]:
        if not cfg.wordiness_enabled:
            return []
        content = chapter.content
        skipped = non_prose_spans(content)
        quotes = find_double_quote_spans(content)
        findings: list[Finding] = []
        # Longer phrases first via _PHRASES order; skip overlapping hits.
        claimed: list[tuple[int, int]] = []
        for pattern, replacement, rule_id in _COMPILED:
            for match in pattern.finditer(content):
                start, end = match.start(), match.end()
                if span_overlaps_any(start, end, skipped):
                    continue
                if in_any_span(start, quotes):
                    continue
                if any(start < c_end and c_start < end for c_start, c_end in claimed):
                    continue
                old = match.group(0)
                fixed = _preserve_case(old, replacement)
                message = (
                    f"Prefer '{fixed}' over '{old}'."
                    if fixed
                    else f"Consider dropping '{old}'."
                )
                findings.append(
                    Finding(
                        id="",
                        category=Category.WORDINESS,
                        severity=Severity.SUGGESTION,
                        message=message,
                        location=location_from_span(chapter, start, end, excerpt=old),
                        engine=Engine.DETERMINISTIC,
                        suggestion=fixed,
                        rule_id=rule_id,
                        applyable=True,
                        replacement=fixed,
                        metadata={"expected_old": old},
                    )
                )
                claimed.append((start, end))
        return findings


def _preserve_case(original: str, replacement: str) -> str:
    if not replacement:
        return ""
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


__all__ = ["WordinessChecker", "_PHRASES"]
