"""Ask TypeSafe whether an LLM garble flag is really broken text.

Close point-of-view often corrects itself: a phrase, an ellipsis, then
"No," then the sharper wording. That is voice. TypeSafe sees the
surrounding prose and keeps only the flags it calls garbled.
"""

from __future__ import annotations

import logging
from typing import Any

from ghostcopyeditor.canon import CastMember, cast_lines
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.lexicon import Lexicon
from ghostcopyeditor.models.finding import Finding
from ghostcopyeditor.typesafe.client import ask

logger = logging.getLogger(__name__)

_RADIUS = 500
_QUESTION = "copy.garbled_or_voice"

_INSTRUCTIONS = (
    "Read flagged_excerpt inside surrounding_prose. "
    "Choose garbled only when a reader would stumble: a dropped word, "
    "keyboard mash, or a mid-edit scrap that was not meant to stay. "
    "Choose voice when the point of view corrects itself on purpose "
    "(an ellipsis, then No, then a clearer phrase) or the line is "
    "finished style. Book lexicon terms and special spellings are intentional. "
    "Names in book_cast are real people. Do not call a name garbled. "
    "Use only the pronouns listed for that person."
)

_CRITERIA = {
    "garbled": "Actually broken text a reader would stumble on",
    "voice": "Intentional style, including inner-monologue self-correction",
}


def surrounding_prose(chapter: Chapter, finding: Finding) -> str:
    """Return prose around the flagged span, about a thousand characters."""
    content = chapter.content
    start = finding.location.char_start
    end = finding.location.char_end
    excerpt = finding.location.excerpt or ""
    if start is None or end is None:
        idx = content.find(excerpt) if excerpt else -1
        if idx < 0:
            return excerpt
        start, end = idx, idx + len(excerpt)
    left = max(0, start - _RADIUS)
    right = min(len(content), end + _RADIUS)
    return content[left:right]


def garbled_review_questions() -> dict[str, Any]:
    """One Choice: garbled or voice."""
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


def _disarm(finding: Finding) -> None:
    finding.applyable = False
    finding.replacement = None


async def review_garbled_findings(
    chapter: Chapter,
    findings: list[Finding],
    typesafe_client: Any | None,
    cfg: GhostCopyeditorConfig,
    lexicon: Lexicon | None = None,
    cast: tuple[CastMember, ...] = (),
) -> list[Finding]:
    """Drop voice. Keep confirmed garble. Unconfirmed garble is not applyable."""
    book = lexicon or Lexicon()
    if typesafe_client is None:
        for finding in findings:
            if finding.rule_id == "llm.garbled":
                _disarm(finding)
        return findings

    questions = garbled_review_questions()
    kept: list[Finding] = []
    for finding in findings:
        if finding.rule_id != "llm.garbled":
            kept.append(finding)
            continue
        state = {
            "surrounding_prose": surrounding_prose(chapter, finding),
            "flagged_excerpt": finding.location.excerpt,
            "proposed_replacement": finding.suggestion or "",
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
                "TypeSafe garble review failed for chapter %s",
                chapter.chapter_number,
            )
            _disarm(finding)
            kept.append(finding)
            continue
        label, confidence = _label_and_confidence(response)
        finding.metadata["garbled_review"] = label
        finding.metadata["garbled_review_confidence"] = confidence
        if label == "voice":
            continue
        if label != "garbled" or confidence < cfg.typesafe_confidence_floor:
            _disarm(finding)
        kept.append(finding)
    return kept


def drop_brute_echo(findings: list[Finding]) -> list[Finding]:
    """Remove sliding-window echo counts. They are not informed notes."""
    return [f for f in findings if f.rule_id != "echo.local_repeat"]


__all__ = [
    "drop_brute_echo",
    "review_garbled_findings",
    "surrounding_prose",
]
