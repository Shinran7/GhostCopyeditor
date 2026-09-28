"""Earth timeline / culture anachronism checker (eff33fcf / #274 T2).

Report-only under Category.STYLE with rule_id anachronism.earth_timeline.
Does not add a new Category value (KD-18).
"""

from __future__ import annotations

import re
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

# Fail-closed eon/era + optional Earth infrastructure lexicon (checker-local).
_EARTH_TIMELINE_TERMS: tuple[str, ...] = (
    "pre-cambrian",
    "precambrian",
    "cambrian",
    "ordovician",
    "silurian",
    "devonian",
    "carboniferous",
    "permian",
    "triassic",
    "jurassic",
    "cretaceous",
    "paleogene",
    "neogene",
    "pleistocene",
    "holocene",
    "mesozoic",
    "paleozoic",
    "cenozoic",
    "archean",
    "proterozoic",
    "telephone pole",
    "telephone poles",
    "roman empire",
    "victorian era",
    "medieval europe",
)

_EARTH_SETTING_CUES = re.compile(
    r"\b(?:Earth|Terra|Sol\s+system|United\s+States|London|Paris|Rome|Tokyo)\b",
    re.IGNORECASE,
)

_COMPILED: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (
        re.compile(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", re.IGNORECASE),
        term,
    )
    for term in _EARTH_TIMELINE_TERMS
)


class AnachronismChecker:
    """Earth timeline/culture labels on non-Earth prose — STYLE, report-only."""

    rule_ids: ClassVar[tuple[str, ...]] = ("anachronism.earth_timeline",)

    def check(self, chapter: Chapter, cfg: GhostCopyeditorConfig) -> list[Finding]:
        del cfg
        content = chapter.content
        skipped = non_prose_spans(content)
        earthish = bool(_EARTH_SETTING_CUES.search(content))
        findings: list[Finding] = []
        seen: set[str] = set()
        for pattern, term in _COMPILED:
            for match in pattern.finditer(content):
                start, end = match.start(), match.end()
                if span_overlaps_any(start, end, skipped):
                    continue
                key = f"{term.lower()}:{start}"
                if key in seen:
                    continue
                seen.add(key)
                if earthish:
                    # Intentional Earth POV / setting — demote to quiet skip.
                    continue
                excerpt = match.group(0)
                findings.append(
                    Finding(
                        id="",
                        category=Category.STYLE,
                        severity=Severity.SUGGESTION,
                        message=(
                            f"Earth timeline/culture label '{excerpt}' appears in "
                            "prose that does not establish an Earth setting. Prefer "
                            "in-world chronology or a local simile."
                        ),
                        location=location_from_span(chapter, start, end, excerpt=excerpt),
                        engine=Engine.DETERMINISTIC,
                        suggestion=(
                            "Replace with world-local time/material language, or "
                            "mark the setting as Earth if intentional."
                        ),
                        rule_id="anachronism.earth_timeline",
                        applyable=False,
                        replacement=None,
                        metadata={"term": term.lower()},
                    )
                )
        return findings


__all__ = ["AnachronismChecker"]
