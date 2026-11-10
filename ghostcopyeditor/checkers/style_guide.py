"""Per-book style guide: banned phrases, pet-word limits, house spellings.

Set in ``config.yaml``::

    style_guide:
      banned: ["a beat", "let out a breath"]
      pet_words: {"suddenly": 2, "the weight of": 1}
      spellings: {"grey": "gray"}

Matching ignores case and respects word edges. Frontmatter, code, headings,
and scene breaks are skipped. House spellings are applyable; a spelling that
is a worldbuilding term is dropped later by the lexicon check.
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


def _pattern(phrase: str) -> re.Pattern[str]:
    words = [re.escape(w) for w in phrase.split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)", re.IGNORECASE)


def _match_case(old: str, new: str) -> str:
    if old.isupper() and len(old) > 1:
        return new.upper()
    if old[:1].isupper():
        return new[:1].upper() + new[1:]
    return new


class StyleGuideChecker:
    """Rules from the book's own style guide (``guide.*``)."""

    rule_ids: ClassVar[tuple[str, ...]] = (
        "guide.banned",
        "guide.pet_word",
        "guide.spelling",
    )

    def check(self, chapter: Chapter, cfg: GhostCopyeditorConfig) -> list[Finding]:
        guide = cfg.style_guide
        if not (guide.banned or guide.pet_words or guide.spellings):
            return []
        text = chapter.content
        skipped = non_prose_spans(text)

        def matches(phrase: str) -> list[re.Match[str]]:
            if not phrase.strip():
                return []
            return [
                m
                for m in _pattern(phrase).finditer(text)
                if not span_overlaps_any(m.start(), m.end(), skipped)
            ]

        def finding(
            match: re.Match[str], rule: str, severity: Severity, message: str, **extra: object
        ) -> Finding:
            replacement = extra.pop("replacement", None)
            return Finding(
                id="",
                category=Category.STYLE,
                severity=severity,
                message=message,
                location=location_from_span(chapter, match.start(), match.end()),
                engine=Engine.DETERMINISTIC,
                suggestion=str(replacement) if replacement else "(per the book's style guide)",
                rule_id=rule,
                applyable=replacement is not None,
                replacement=str(replacement) if replacement else None,
                metadata={"expected_old": match.group(0), **extra},
            )

        findings: list[Finding] = []
        for phrase in guide.banned:
            for m in matches(phrase):
                findings.append(
                    finding(
                        m, "guide.banned", Severity.WARNING,
                        f"“{m.group(0)}” is on this book's banned list.",
                        phrase=phrase,
                    )
                )
        for phrase, limit in guide.pet_words.items():
            found = matches(phrase)
            if len(found) <= limit:
                continue
            for m in found:
                findings.append(
                    finding(
                        m, "guide.pet_word", Severity.SUGGESTION,
                        f"“{phrase}” appears {len(found)} times in this chapter "
                        f"(limit {limit}).",
                        phrase=phrase, count=len(found), limit=limit,
                    )
                )
        for wrong, right in guide.spellings.items():
            for m in matches(wrong):
                if m.group(0) == _match_case(m.group(0), right):
                    continue
                fixed = _match_case(m.group(0), right)
                findings.append(
                    finding(
                        m, "guide.spelling", Severity.SUGGESTION,
                        f"House spelling: “{fixed}”.",
                        replacement=fixed,
                    )
                )
        return findings


__all__ = ["StyleGuideChecker"]
