"""Adapt TypeSafe Choice/Noul answers into Finding records."""

from __future__ import annotations

from typing import Any

from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Location,
    Severity,
    location_from_span,
)
from ghostcopyeditor.typesafe.routing import noul_band

_GRAMMAR_LABELS = frozenset({"error", "warning"})
_STYLE_CONCERN = "concern"


def _anchor_location(
    chapter: Chapter,
    excerpt: str,
    *,
    char_start: int | None = None,
    char_end: int | None = None,
) -> tuple[Location, dict[str, Any]]:
    """Locate *excerpt* in chapter content; mark unanchored when not found."""
    content = chapter.content
    meta: dict[str, Any] = {}

    if (
        char_start is not None
        and char_end is not None
        and 0 <= char_start < char_end <= len(content)
    ):
        return (
            location_from_span(
                chapter, char_start, char_end, excerpt=excerpt or content[char_start:char_end]
            ),
            meta,
        )

    needle = (excerpt or "").strip()
    if needle.endswith("…"):
        needle = needle[:-1]
    if needle:
        idx = content.find(needle)
        if idx >= 0:
            return location_from_span(chapter, idx, idx + len(needle), excerpt=needle), meta

    meta["unanchored"] = True
    return (
        Location(
            chapter_number=chapter.chapter_number,
            chapter_path=str(chapter.source_path),
            excerpt=excerpt or "",
        ),
        meta,
    )


def _first_span(
    candidate_spans: list[dict[str, Any]],
) -> tuple[str, int | None, int | None]:
    if not candidate_spans:
        return "", None, None
    first = candidate_spans[0]
    return (
        str(first.get("text", "")),
        first.get("char_start"),
        first.get("char_end"),
    )


def _choice_grammar_finding(
    answer: Any,
    chapter: Chapter,
    *,
    confidence_floor: float,
    candidate_spans: list[dict[str, Any]],
) -> Finding | None:
    label = str(getattr(answer, "choice", "") or "").lower()
    confidence = float(getattr(answer, "confidence", 0.0) or 0.0)
    if label not in _GRAMMAR_LABELS or confidence < confidence_floor:
        return None
    excerpt, start, end = _first_span(candidate_spans)
    location, meta = _anchor_location(chapter, excerpt, char_start=start, char_end=end)
    severity = Severity.ERROR if label == "error" else Severity.WARNING
    message = (
        f"TypeSafe grammar {label}: review this passage for an actionable defect."
    )
    if location.excerpt:
        message = f"{message} Excerpt: {location.excerpt[:120]}"
    return Finding(
        id="",
        category=Category.GRAMMAR,
        severity=severity,
        message=message,
        location=location,
        engine=Engine.TYPESAFE,
        rule_id="copy.grammar_ambiguity",
        applyable=False,
        confidence=confidence,
        metadata=meta,
    )


def _choice_style_finding(
    answer: Any,
    chapter: Chapter,
    *,
    confidence_floor: float,
) -> Finding | None:
    label = str(getattr(answer, "choice", "") or "").lower()
    confidence = float(getattr(answer, "confidence", 0.0) or 0.0)
    if label != _STYLE_CONCERN or confidence < confidence_floor:
        return None
    # Prefer a short head of prose for anchoring when no candidate spans apply.
    head = chapter.content.strip()[:200]
    location, meta = _anchor_location(chapter, head)
    return Finding(
        id="",
        category=Category.STYLE,
        severity=Severity.WARNING,
        message="TypeSafe style concern: sudden register clash or tense wobble.",
        location=location,
        engine=Engine.TYPESAFE,
        rule_id="copy.style_consistency",
        applyable=False,
        confidence=confidence,
        metadata=meta,
    )


def _noul_finding(
    *,
    rule_id: str,
    category: Category,
    answer: Any,
    chapter: Chapter,
    positive_threshold: float,
    candidate_spans: list[dict[str, Any]],
    preferred_source: str | None = None,
) -> Finding | None:
    value = float(getattr(answer, "noul", 0.0) or 0.0)
    if noul_band(value, positive_threshold=positive_threshold) != "positive":
        return None

    spans = candidate_spans
    if preferred_source:
        preferred = [s for s in candidate_spans if s.get("source") == preferred_source]
        if preferred:
            spans = preferred
    excerpt, start, end = _first_span(spans)
    location, meta = _anchor_location(chapter, excerpt, char_start=start, char_end=end)
    meta = {**meta, "noul": value}
    label = "echo" if category == Category.ECHO else "wordiness"
    message = f"TypeSafe {label} judgment: likely issue in context (noul={value:.2f})."
    if location.excerpt:
        message = f"{message} Excerpt: {location.excerpt[:120]}"
    return Finding(
        id="",
        category=category,
        severity=Severity.SUGGESTION,
        message=message,
        location=location,
        engine=Engine.TYPESAFE,
        rule_id=rule_id,
        applyable=False,
        confidence=value,
        metadata=meta,
    )


def response_to_findings(
    response: Any,
    chapter: Chapter,
    *,
    confidence_floor: float = 0.55,
    positive_threshold: float = 0.65,
    candidate_spans: list[dict[str, Any]] | None = None,
) -> list[Finding]:
    """Map a System One response to non-applyable Finding records."""
    spans = list(candidate_spans or [])
    findings: list[Finding] = []

    choices = getattr(response, "choices", {}) or {}
    grammar = choices.get("copy.grammar_ambiguity")
    if grammar is not None:
        finding = _choice_grammar_finding(
            grammar,
            chapter,
            confidence_floor=confidence_floor,
            candidate_spans=spans,
        )
        if finding is not None:
            findings.append(finding)

    style = choices.get("copy.style_consistency")
    if style is not None:
        finding = _choice_style_finding(
            style, chapter, confidence_floor=confidence_floor
        )
        if finding is not None:
            findings.append(finding)

    nouls = getattr(response, "nouls", {}) or {}
    echo = nouls.get("copy.echo_context")
    if echo is not None:
        finding = _noul_finding(
            rule_id="copy.echo_context",
            category=Category.ECHO,
            answer=echo,
            chapter=chapter,
            positive_threshold=positive_threshold,
            candidate_spans=spans,
            preferred_source="echo",
        )
        if finding is not None:
            findings.append(finding)

    wordiness = nouls.get("copy.wordiness_context")
    if wordiness is not None:
        finding = _noul_finding(
            rule_id="copy.wordiness_context",
            category=Category.WORDINESS,
            answer=wordiness,
            chapter=chapter,
            positive_threshold=positive_threshold,
            candidate_spans=spans,
            preferred_source="wordiness",
        )
        if finding is not None:
            findings.append(finding)

    return findings
