"""Per-hit TypeSafe confirm for missing-predicate findings."""

from __future__ import annotations

import logging
from typing import Any

from ghostcopyeditor.canon import CastMember, cast_lines
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.lexicon import Lexicon
from ghostcopyeditor.models.finding import Finding, Severity
from ghostcopyeditor.typesafe.client import ask
from ghostcopyeditor.typesafe.garbled_review import surrounding_prose
from ghostcopyeditor.typesafe.per_hit_budget import PerHitAskBudget

logger = logging.getLogger(__name__)

_QUESTION = "copy.missing_predicate"

_INSTRUCTIONS = (
    "Read flagged_excerpt inside surrounding_prose. "
    "The tree flagged a period-terminated sentence whose main clause may "
    "lack a finite verb (predicate). ROOT tags are in root_text / root_pos / "
    "root_tag. Choose broken when a reader would stumble on a missing main "
    "verb. Choose intentional when the line is deliberate fragment voice or "
    "a finished stylistic choice. Book lexicon terms are intentional. "
    "Names in book_cast are real people."
)

_CRITERIA = {
    "broken": "Main clause is missing a finite verb; reader would stumble",
    "intentional": "Deliberate fragment or finished stylistic voice",
}


def missing_predicate_review_questions() -> dict[str, Any]:
    """One Choice: broken or intentional."""
    from typesafe_sdk import Choice

    return {
        _QUESTION: Choice(
            instructions=_INSTRUCTIONS,
            criteria=dict(_CRITERIA),
        )
    }


def _label_and_confidence(response: Any) -> tuple[str, float]:
    choices = getattr(response, "choices", {}) or {}
    answer = choices.get(_QUESTION)
    if answer is None and isinstance(choices, dict):
        answer = next(iter(choices.values()), None)
    label = str(getattr(answer, "choice", "") or "").strip().lower()
    confidence = float(getattr(answer, "confidence", 0.0) or 0.0)
    return label, confidence


async def review_missing_predicate_findings(
    chapter: Chapter,
    findings: list[Finding],
    typesafe_client: Any | None,
    cfg: GhostCopyeditorConfig,
    lexicon: Lexicon | None = None,
    cast: tuple[CastMember, ...] = (),
    *,
    budget: PerHitAskBudget | None = None,
) -> list[Finding]:
    """Demote intentional to INFO; keep broken as WARNING; fail-open keep WARNING."""
    if not cfg.missing_predicate_typesafe_confirm:
        return findings
    if typesafe_client is None:
        return findings

    book = lexicon or Lexicon()
    questions = missing_predicate_review_questions()
    out: list[Finding] = []
    for finding in findings:
        if finding.rule_id != "mech.missing_predicate":
            out.append(finding)
            continue
        if budget is not None and not budget.try_consume():
            # Budget exhausted — keep WARNING unreviewed.
            finding.metadata["missing_predicate_review"] = "budget_exhausted"
            out.append(finding)
            continue
        state = {
            "surrounding_prose": surrounding_prose(chapter, finding),
            "flagged_excerpt": finding.location.excerpt,
            "root_text": finding.metadata.get("root_text", ""),
            "root_pos": finding.metadata.get("root_pos", ""),
            "root_tag": finding.metadata.get("root_tag", ""),
            "book_lexicon": book.prompt_lines(),
            "book_cast": cast_lines(cast),
        }
        try:
            response = await ask(
                typesafe_client,
                state=state,
                questions=questions,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "TypeSafe missing-predicate review failed for chapter %s",
                chapter.chapter_number,
            )
            out.append(finding)
            continue
        label, confidence = _label_and_confidence(response)
        finding.metadata["missing_predicate_review"] = label
        finding.metadata["missing_predicate_review_confidence"] = confidence
        if (
            label == "intentional"
            and confidence >= cfg.typesafe_confidence_floor
        ):
            finding.severity = Severity.INFO
        out.append(finding)
    return out


__all__ = [
    "missing_predicate_review_questions",
    "review_missing_predicate_findings",
]
