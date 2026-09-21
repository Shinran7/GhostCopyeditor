"""Decide when a suggested rewrite is safe for a program to apply.

A paste is safe only for a pure deletion, or a one-word grammar tweak
such as "It" to "Its". Adding a new name or a new verb is not safe.
Pronoun swaps are guesses about the cast and are not filed.
"""

from __future__ import annotations

import re

from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import Finding

# A substitution longer than this on both sides is a rewrite, not a repair.
_MAX_SUBSTITUTION_CHARS = 12
_WORD_RE = re.compile(r"[A-Za-z']+")
_PRONOUN_GUESS = re.compile(
    r"pronoun|gender|referring to|instead of ['\"](?:him|her|he|she)\b",
    re.IGNORECASE,
)
_PRONOUN_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"it", "its", "it's"}),
    frozenset({"i", "me", "my", "mine", "myself"}),
    frozenset({"you", "your", "yours", "yourself", "yourselves"}),
    frozenset({"he", "him", "his", "himself"}),
    frozenset({"she", "her", "hers", "herself"}),
    frozenset({"we", "us", "our", "ours", "ourselves"}),
    frozenset({"they", "them", "their", "theirs", "themself", "themselves"}),
)


def is_single_repair(old: str, new: str) -> bool:
    """True when *new* is *old* with one insertion, deletion, or short swap."""
    if not old or not new or old == new:
        return False
    prefix_len = 0
    limit = min(len(old), len(new))
    while prefix_len < limit and old[prefix_len] == new[prefix_len]:
        prefix_len += 1
    suffix_len = 0
    while (
        suffix_len < (limit - prefix_len)
        and old[len(old) - 1 - suffix_len] == new[len(new) - 1 - suffix_len]
    ):
        suffix_len += 1
    removed = old[prefix_len : len(old) - suffix_len if suffix_len else len(old)]
    added = new[prefix_len : len(new) - suffix_len if suffix_len else len(new)]
    if len(removed) > _MAX_SUBSTITUTION_CHARS and len(added) > _MAX_SUBSTITUTION_CHARS:
        return False
    if prefix_len + suffix_len == 0 and len(old) > 24:
        return False
    return True


def _diff_parts(old: str, new: str) -> tuple[str, str]:
    prefix_len = 0
    limit = min(len(old), len(new))
    while prefix_len < limit and old[prefix_len] == new[prefix_len]:
        prefix_len += 1
    suffix_len = 0
    while (
        suffix_len < (limit - prefix_len)
        and old[len(old) - 1 - suffix_len] == new[len(new) - 1 - suffix_len]
    ):
        suffix_len += 1
    removed = old[prefix_len : len(old) - suffix_len if suffix_len else len(old)]
    added = new[prefix_len : len(new) - suffix_len if suffix_len else len(new)]
    return removed, added


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _pronoun_family(word: str) -> int | None:
    key = word.casefold()
    for index, family in enumerate(_PRONOUN_FAMILIES):
        if key in family:
            return index
    return None


def is_pure_deletion(old: str, new: str) -> bool:
    """True when *new* only removes text. No new word is introduced."""
    if not old or not new or old == new:
        return False
    removed, added = _diff_parts(old, new)
    return bool(removed.strip()) and not _words(added)


def is_one_word_grammar(old: str, new: str) -> bool:
    """True for a clitic tweak of one existing word, such as It to Its."""
    if not old or not new or old == new:
        return False
    removed, added = _diff_parts(old, new)
    if not _words(removed) and added.lower() in {"s", "'s", "'"}:
        return True
    if _words(removed) or len(_words(added)) != 1:
        return False
    old_words = _words(removed)
    new_words = _words(added)
    if len(old_words) == 1 and len(new_words) == 1:
        left = _pronoun_family(old_words[0])
        right = _pronoun_family(new_words[0])
        return left is not None and left == right
    return False


def is_safe_to_paste(old: str, new: str) -> bool:
    """True only for a pure deletion or a one-word grammar fix."""
    return is_pure_deletion(old, new) or is_one_word_grammar(old, new)


def is_pronoun_guess(old: str, new: str, message: str = "") -> bool:
    """True when the note swaps person or gender, not It to Its."""
    if is_one_word_grammar(old, new):
        return False
    old_families = {
        family
        for word in _words(old)
        if (family := _pronoun_family(word)) is not None
    }
    new_families = {
        family
        for word in _words(new)
        if (family := _pronoun_family(word)) is not None
    }
    if old_families != new_families and (old_families or new_families):
        return True
    if new and _PRONOUN_GUESS.search(message or ""):
        return True
    return False


def drop_pronoun_guesses(findings: list[Finding]) -> list[Finding]:
    """Leave pronoun swaps out of the report. A wrong cast sniff is worse."""
    kept: list[Finding] = []
    for finding in findings:
        old = finding.location.excerpt or ""
        new = (finding.suggestion or finding.replacement or "").strip()
        if finding.rule_id == "llm.garbled" and is_pronoun_guess(
            old, new, finding.message
        ):
            continue
        kept.append(finding)
    return kept


def mark_program_replacement(finding: Finding, chapter: Chapter) -> None:
    """Fill ``replacement`` and ``applyable`` only for a unique single repair."""
    suggestion = (finding.suggestion or "").strip()
    excerpt = finding.location.excerpt or ""
    content = chapter.content
    start = finding.location.char_start
    end = finding.location.char_end
    anchored = (
        start is not None
        and end is not None
        and not finding.metadata.get("unanchored")
        and content[start:end] == excerpt
    )
    unique = bool(excerpt) and content.count(excerpt) == 1
    if anchored and unique and is_safe_to_paste(excerpt, suggestion):
        finding.applyable = True
        finding.replacement = suggestion
        finding.metadata["expected_old"] = excerpt
        return
    finding.applyable = False
    finding.replacement = None


__all__ = [
    "drop_pronoun_guesses",
    "is_one_word_grammar",
    "is_pronoun_guess",
    "is_pure_deletion",
    "is_safe_to_paste",
    "is_single_repair",
    "mark_program_replacement",
]
