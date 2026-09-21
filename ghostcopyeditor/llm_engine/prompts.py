"""Prompt templates for LLM garbled detection."""

from __future__ import annotations

GARBLED_SYSTEM_PROMPT = """\
You are a fiction copy editor. Find garbled, broken, or mid-edit wreckage \
in the chapter text. Look for dropped words, duplicated clauses, keyboard \
smash, truncated sentences, and nonsense that a reader would stumble on.

Return ONLY a JSON array. No markdown fences. No commentary.
Each item must be an object with these keys:
  - "excerpt": exact substring from the chapter (copy it verbatim)
  - "message": short plain description of the problem
  - "suggestion": a repaired rewrite of that excerpt
  - "severity": one of "error", "warning", "suggestion"

If nothing is garbled, return [].
Do not invent issues. Prefer precision over volume.
"""


def build_garbled_user_prompt(chapter_content: str, *, chapter_number: int) -> str:
    """Build the user message for garbled detection on one chapter."""
    return (
        f"Chapter {chapter_number:03d} text follows between <chapter> tags.\n"
        f"<chapter>\n{chapter_content}\n</chapter>\n"
        "Return the JSON array of garbled findings now."
    )


__all__ = [
    "GARBLED_SYSTEM_PROMPT",
    "build_garbled_user_prompt",
]
