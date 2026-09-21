"""Grammar/mechanics deterministic rules."""

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

_DOUBLE_SPACE_RE = re.compile(r" {2,}")
_TRAILING_WS_RE = re.compile(r"[ \t]+(?=\r?\n)|[ \t]+$")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"(\w) ([,:;])")
_REPEATED_BANG_RE = re.compile(r"!{2,}")
_REPEATED_Q_RE = re.compile(r"\?{2,}")


class MechanicsChecker:
    """Ship + report-only mechanics rules."""

    rule_ids: ClassVar[tuple[str, ...]] = (
        "mech.double_space",
        "mech.trailing_ws",
        "mech.space_before_punct",
        "mech.repeated_punct",
    )

    def check(self, chapter: Chapter, cfg: GhostCopyeditorConfig) -> list[Finding]:
        del cfg  # mechanics ignore config knobs in v1
        content = chapter.content
        skipped = non_prose_spans(content)
        quotes = find_double_quote_spans(content)
        findings: list[Finding] = []
        findings.extend(_double_spaces(chapter, content, skipped))
        findings.extend(_trailing_ws(chapter, content, skipped))
        findings.extend(_space_before_punct(chapter, content, skipped, quotes))
        findings.extend(_repeated_punct(chapter, content, skipped))
        return findings


def _double_spaces(
    chapter: Chapter, content: str, skipped: list
) -> list[Finding]:
    findings: list[Finding] = []
    for match in _DOUBLE_SPACE_RE.finditer(content):
        start, end = match.start(), match.end()
        if span_overlaps_any(start, end, skipped):
            continue
        # Preserve leading indent and leave pure trailing runs to trailing_ws.
        if start == 0 or content[start - 1] == "\n":
            continue
        if end == len(content) or content[end] == "\n":
            continue
        old = match.group(0)
        findings.append(
            Finding(
                id="",
                category=Category.GRAMMAR,
                severity=Severity.ERROR,
                message="Collapse multiple spaces to one.",
                location=location_from_span(chapter, start, end, excerpt=old),
                engine=Engine.DETERMINISTIC,
                suggestion=" ",
                rule_id="mech.double_space",
                applyable=True,
                replacement=" ",
                metadata={"expected_old": old},
            )
        )
    return findings


def _trailing_ws(
    chapter: Chapter, content: str, skipped: list
) -> list[Finding]:
    findings: list[Finding] = []
    for match in _TRAILING_WS_RE.finditer(content):
        start, end = match.start(), match.end()
        if span_overlaps_any(start, end, skipped):
            continue
        old = match.group(0)
        findings.append(
            Finding(
                id="",
                category=Category.GRAMMAR,
                severity=Severity.ERROR,
                message="Strip trailing whitespace.",
                location=location_from_span(chapter, start, end, excerpt=old),
                engine=Engine.DETERMINISTIC,
                suggestion="",
                rule_id="mech.trailing_ws",
                applyable=True,
                replacement="",
                metadata={"expected_old": old},
            )
        )
    return findings


def _space_before_punct(
    chapter: Chapter, content: str, skipped: list, quotes: list
) -> list[Finding]:
    findings: list[Finding] = []
    for match in _SPACE_BEFORE_PUNCT_RE.finditer(content):
        # Span is the space + punctuation: " ,"
        start = match.start(1) + 1  # space
        end = match.end()  # after punct
        if span_overlaps_any(start, end, skipped):
            continue
        # Skip inside dialogue quotes (fiction dialect / intensity).
        if in_any_span(start, quotes):
            continue
        old = content[start:end]
        punct = match.group(2)
        findings.append(
            Finding(
                id="",
                category=Category.GRAMMAR,
                severity=Severity.ERROR,
                message=f"Remove space before '{punct}'.",
                location=location_from_span(chapter, start, end, excerpt=old),
                engine=Engine.DETERMINISTIC,
                suggestion=punct,
                rule_id="mech.space_before_punct",
                applyable=True,
                replacement=punct,
                metadata={"expected_old": old},
            )
        )
    return findings


def _repeated_punct(
    chapter: Chapter, content: str, skipped: list
) -> list[Finding]:
    findings: list[Finding] = []
    for pattern, label in ((_REPEATED_BANG_RE, "!"), (_REPEATED_Q_RE, "?")):
        for match in pattern.finditer(content):
            start, end = match.start(), match.end()
            if span_overlaps_any(start, end, skipped):
                continue
            old = match.group(0)
            findings.append(
                Finding(
                    id="",
                    category=Category.GRAMMAR,
                    severity=Severity.WARNING,
                    message=(
                        f"Repeated '{label}' punctuation may be intentional "
                        "fiction intensity."
                    ),
                    location=location_from_span(chapter, start, end, excerpt=old),
                    engine=Engine.DETERMINISTIC,
                    suggestion=label,
                    rule_id="mech.repeated_punct",
                    applyable=False,
                    replacement=None,
                    metadata={},
                )
            )
    return findings


__all__ = ["MechanicsChecker"]
