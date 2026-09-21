"""Style consistency hooks (report-only in v1)."""

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

# Unicode em dash, or ASCII `--` that is not part of a `---` scene break / fence.
_EM_DASH_RE = re.compile(r"\u2014|(?<!-)-{2}(?!-)")


class StyleChecker:
    """Report-only style rules. Em dash is never auto-rewritten."""

    rule_ids: ClassVar[tuple[str, ...]] = ("style.em_dash",)

    def check(self, chapter: Chapter, cfg: GhostCopyeditorConfig) -> list[Finding]:
        del cfg
        content = chapter.content
        skipped = non_prose_spans(content)
        findings: list[Finding] = []
        for match in _EM_DASH_RE.finditer(content):
            start, end = match.start(), match.end()
            if span_overlaps_any(start, end, skipped):
                continue
            old = match.group(0)
            findings.append(
                Finding(
                    id="",
                    category=Category.STYLE,
                    severity=Severity.SUGGESTION,
                    message=(
                        "Em dash or double hyphen found. Prefer a period or "
                        "parentheses for this project."
                    ),
                    location=location_from_span(chapter, start, end, excerpt=old),
                    engine=Engine.DETERMINISTIC,
                    suggestion="(rewrite with a period or parentheses)",
                    rule_id="style.em_dash",
                    applyable=False,
                    replacement=None,
                    metadata={},
                )
            )
        return findings


__all__ = ["StyleChecker"]
