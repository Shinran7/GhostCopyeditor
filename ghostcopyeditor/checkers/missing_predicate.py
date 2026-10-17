"""Missing-predicate deterministic checker (shared spaCy detector)."""

from __future__ import annotations

from typing import ClassVar

from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Severity,
    location_from_span,
)
from ghostcopyeditor.nlp import detect_missing_predicates


class MissingPredicateChecker:
    """Report-only: period-terminated sentence with no finite predicate."""

    rule_ids: ClassVar[tuple[str, ...]] = ("mech.missing_predicate",)

    def check(self, chapter: Chapter, cfg: GhostCopyeditorConfig) -> list[Finding]:
        if not cfg.missing_predicate_enabled:
            return []
        hits = detect_missing_predicates(
            chapter.content,
            min_tokens=cfg.missing_predicate_min_tokens,
            skip_dialogue_heavy=cfg.missing_predicate_skip_dialogue_heavy,
            require_period=cfg.missing_predicate_require_period,
            non_prose=None,
        )
        findings: list[Finding] = []
        for hit in hits:
            findings.append(
                Finding(
                    id="",
                    category=Category.GRAMMAR,
                    severity=Severity.WARNING,
                    message="Main clause may be missing a finite verb (predicate).",
                    location=location_from_span(
                        chapter, hit.start, hit.end, excerpt=hit.excerpt
                    ),
                    engine=Engine.DETERMINISTIC,
                    suggestion=None,
                    rule_id="mech.missing_predicate",
                    applyable=False,
                    replacement=None,
                    metadata={
                        "root_text": hit.root_text,
                        "root_pos": hit.root_pos,
                        "root_tag": hit.root_tag,
                    },
                )
            )
        return findings


__all__ = ["MissingPredicateChecker"]
