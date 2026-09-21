"""Copy-edit TypeSafe Choice/Noul question bank."""

from __future__ import annotations

from typing import Any

GRAMMAR_CRITERIA: dict[str, str] = {
    "error": "Actionable grammar defect that hurts correctness",
    "warning": "Likely grammar issue worth flagging",
    "ok": "No actionable grammar defect beyond deterministic coverage",
}

STYLE_CRITERIA: dict[str, str] = {
    "concern": "Sudden register clash or tense wobble inside the prose",
    "ok": "Register and tense are consistent enough",
}

COPY_EDIT_QUESTIONS: tuple[str, ...] = (
    "copy.grammar_ambiguity",
    "copy.style_consistency",
    "copy.echo_context",
    "copy.wordiness_context",
)

_CHOICE_INSTRUCTIONS: dict[str, str] = {
    "copy.grammar_ambiguity": (
        "Judge actionable grammar defects in candidate_passages that "
        "deterministic rules did not already cover. Prefer error or warning "
        "only when the defect is clear; otherwise ok."
    ),
    "copy.style_consistency": (
        "Judge sudden register clash or tense wobble inside the capped prose. "
        "Use concern only when the clash is clear; otherwise ok."
    ),
}

_NOUL_INSTRUCTIONS: dict[str, str] = {
    "copy.echo_context": (
        "Probability that accidental word echo in the candidate passages "
        "hurts the reading experience."
    ),
    "copy.wordiness_context": (
        "Probability that phrasing in the candidate passages is padded "
        "given the surrounding prose."
    ),
}


def copy_edit_questions() -> dict[str, Any]:
    """Return the v1 copy-edit Choice + Noul question set."""
    from typesafe_sdk import Choice, Noul

    return {
        "copy.grammar_ambiguity": Choice(
            instructions=_CHOICE_INSTRUCTIONS["copy.grammar_ambiguity"],
            criteria=dict(GRAMMAR_CRITERIA),
        ),
        "copy.style_consistency": Choice(
            instructions=_CHOICE_INSTRUCTIONS["copy.style_consistency"],
            criteria=dict(STYLE_CRITERIA),
        ),
        "copy.echo_context": Noul(
            instructions=_NOUL_INSTRUCTIONS["copy.echo_context"],
        ),
        "copy.wordiness_context": Noul(
            instructions=_NOUL_INSTRUCTIONS["copy.wordiness_context"],
        ),
    }
