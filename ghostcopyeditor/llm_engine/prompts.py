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
When a book lexicon is provided, those terms and special spellings are \
intentional. Do not report them as garbled, and do not rewrite them into \
ordinary dictionary words.
When a cast is provided, those names are real people. Do not report a \
name as garbled and do not delete it. Use only the pronouns listed for \
that person. Do not guess a different gender.
"""


def build_garbled_user_prompt(
    chapter_content: str,
    *,
    chapter_number: int,
    lexicon_lines: list[str] | None = None,
    cast_lines: list[str] | None = None,
) -> str:
    """Build the user message for garbled detection on one chapter."""
    lexicon = ""
    if lexicon_lines:
        lexicon = (
            "Book lexicon (intentional spellings and coined words):\n"
            + "\n".join(lexicon_lines)
            + "\n\n"
        )
    cast = ""
    if cast_lines:
        cast = (
            "Cast (name and pronouns from the story's character files):\n"
            + "\n".join(cast_lines)
            + "\n\n"
        )
    return (
        f"{lexicon}{cast}"
        f"Chapter {chapter_number:03d} text follows between <chapter> tags.\n"
        f"<chapter>\n{chapter_content}\n</chapter>\n"
        "Return the JSON array of garbled findings now."
    )


__all__ = [
    "GARBLED_SYSTEM_PROMPT",
    "build_garbled_user_prompt",
]
