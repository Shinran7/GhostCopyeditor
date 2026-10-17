"""Detect period-terminated sentences with no finite predicate."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from ghostcopyeditor.nlp.spacy_runtime import get_nlp

logger = logging.getLogger("ghostcopyeditor.nlp")

# Regions imported lazily inside detect to avoid nlp ↔ checkers package cycle.

_FINITE_TAGS = frozenset({"VBZ", "VBD", "VBP", "MD", "VB"})
_CLEAR_FINITE_TAGS = frozenset({"VBZ", "VBD", "VBP", "MD"})
_FINITE_AUX_DEPS = frozenset({"aux", "auxpass", "cop"})
_PAST_LIKE_TAGS = frozenset({"VBD", "VBN", "VBZ", "VBP"})
_SUBJECT_DEPS = frozenset({"nsubj", "nsubjpass"})
# Period optionally followed by closing quotes/brackets (incl. Unicode closers).
_PERIOD_TERMINAL_RE = re.compile(r'\.[\"\'”’)\]]*$')
_ELLIPSIS_END_RE = re.compile(r"(?:\.\.\.|…)\s*$")
# Quote-only leftovers before a real sentence (spaCy split artifact).
_LEADING_QUOTE_JUNK_RE = re.compile(r'^[\"\'“”]+$')


@dataclass(frozen=True)
class MissingPredicateHit:
    start: int
    end: int
    excerpt: str
    root_text: str
    root_pos: str
    root_tag: str


def _token_is_finite(token: object) -> bool:
    pos = getattr(token, "pos_", "")
    tag = getattr(token, "tag_", "")
    return pos in {"VERB", "AUX"} and tag in _FINITE_TAGS


def _has_mark_child(token: object) -> bool:
    for child in getattr(token, "children", ()):
        if getattr(child, "dep_", "") == "mark":
            return True
    return False


def _ignore_as_main_finite(token: object) -> bool:
    """Skip finites that live in subordinate / absolute clauses.

    ``advcl`` / ``relcl`` verbs (and anything under them) are not the main
    predicate — otherwise \"as he lifted\" quiets a true noun-phrase fragment,
    and \"had bitten\" quiets subjectless \"Leaned …\".

    Unmarked ``acl`` on a noun is *not* ignored here: spaCy often hangs the
    real past tense there (\"The track skidded\").
    """
    dep = getattr(token, "dep_", "")
    if dep in {"advcl", "relcl"}:
        return True
    cur = getattr(token, "head", None)
    seen = 0
    while cur is not None and seen < 32:
        head_dep = getattr(cur, "dep_", "")
        if head_dep in {"advcl", "relcl"}:
            return True
        nxt = getattr(cur, "head", None)
        if nxt is None or nxt is cur:
            break
        cur = nxt
        seen += 1
    return False


def has_finite_predicate(root: object) -> bool:
    """True when the clause has a finite (or imperative) predicate.

    spaCy English often puts the lexical participle on ROOT (VBN) and hangs
    the finite auxiliary as aux / auxpass. Checking only root.tag_ false-flags
    healthy passives and perfects.
    """
    if _token_is_finite(root):
        return True
    children = getattr(root, "children", ())
    for child in children:
        dep = getattr(child, "dep_", "")
        if dep in _FINITE_AUX_DEPS and _token_is_finite(child):
            return True
    return False


def sentence_has_finite_predicate(sent: object) -> bool:
    """True when the sentence has a usable finite main predicate.

    Extends :func:`has_finite_predicate` to quiet spaCy mistags common in
    narrative prose without silencing true fragments:

    - Clear finite tags (VBD/VBZ/VBP/MD) outside marked subordinates
    - VBN with its own nsubj (mistagged narrative past: \"A pop echoed.\")
    - Noun ROOT + unmarked acl past (SVO misparsed as NP: \"The track skidded.\")

    Marked subordinates (``advcl`` + mark, ``relcl``) stay ignored so fixtures
    like \"A rough chatter … as he lifted …\" remain loud.
    """
    root = getattr(sent, "root", None)
    if root is not None and has_finite_predicate(root):
        return True

    for tok in sent:
        tag = getattr(tok, "tag_", "")
        pos = getattr(tok, "pos_", "")
        if _ignore_as_main_finite(tok):
            continue
        if tag in _CLEAR_FINITE_TAGS and pos in {"VERB", "AUX"}:
            return True
        if pos == "VERB" and tag == "VBN":
            if any(
                getattr(c, "dep_", "") in _SUBJECT_DEPS
                for c in getattr(tok, "children", ())
            ):
                return True

    if root is not None and getattr(root, "pos_", "") in {"NOUN", "PROPN"}:
        for child in getattr(root, "children", ()):
            if getattr(child, "dep_", "") != "acl":
                continue
            if getattr(child, "tag_", "") not in _PAST_LIKE_TAGS:
                continue
            if _has_mark_child(child):
                continue
            return True
    return False


def _alphabetic_token_count(sent: object) -> int:
    return sum(1 for tok in sent if getattr(tok, "is_alpha", False))


def _is_dialogue_heavy(sent: object, quote_spans: list) -> bool:
    tokens = list(sent)
    if not tokens:
        return False
    inside = 0
    for tok in tokens:
        start = int(getattr(tok, "idx", -1))
        if start < 0:
            continue
        if any(s.contains(start) for s in quote_spans):
            inside += 1
    return (inside / len(tokens)) >= 0.8


def _period_terminated(text: str) -> bool:
    return _PERIOD_TERMINAL_RE.search(text.rstrip()) is not None


def _ellipsis_soft_voice(text: str, alpha_count: int) -> bool:
    stripped = text.strip()
    if not _ELLIPSIS_END_RE.search(stripped):
        return False
    # Terminator is only ellipsis (no period gate) or short soft voice.
    if not _period_terminated(stripped):
        return True
    return alpha_count < 12


def detect_missing_predicates(
    text: str,
    *,
    min_tokens: int = 5,
    skip_dialogue_heavy: bool = True,
    require_period: bool = True,
    non_prose: list | None = None,
) -> list[MissingPredicateHit]:
    """No usable finite main predicate + quiet gates.

    Uses :func:`sentence_has_finite_predicate` (root/aux plus spaCy-mistag
    guards). Empty if spaCy unavailable. Editor and GCE both call this. Do
    not expose a separate \"raw loud ROOT\" path for product seats.
    """
    from ghostcopyeditor.checkers.regions import (
        find_double_quote_spans,
        non_prose_spans,
        span_overlaps_any,
    )

    nlp = get_nlp()
    if nlp is None:
        return []

    skipped = non_prose if non_prose is not None else non_prose_spans(text)
    quote_spans = find_double_quote_spans(text) if skip_dialogue_heavy else []
    hits: list[MissingPredicateHit] = []

    try:
        doc = nlp(text)
    except Exception:  # noqa: BLE001
        logger.exception("missing_predicate: spaCy parse failed")
        return []

    for sent in doc.sents:
        try:
            start = int(sent.start_char)
            end = int(sent.end_char)
            if span_overlaps_any(start, end, skipped):
                continue
            excerpt = text[start:end]
            stripped = excerpt.strip()
            if not stripped:
                continue
            alpha = _alphabetic_token_count(sent)
            if alpha < min_tokens:
                continue
            if skip_dialogue_heavy and _is_dialogue_heavy(sent, quote_spans):
                continue
            if _ellipsis_soft_voice(stripped, alpha):
                continue
            if require_period and not _period_terminated(stripped):
                continue
            # Drop quote-only junk spans glued onto the next sentence start.
            if _LEADING_QUOTE_JUNK_RE.match(stripped):
                continue
            root = sent.root
            if sentence_has_finite_predicate(sent):
                continue
            hits.append(
                MissingPredicateHit(
                    start=start,
                    end=end,
                    excerpt=stripped,
                    root_text=str(getattr(root, "text", "")),
                    root_pos=str(getattr(root, "pos_", "")),
                    root_tag=str(getattr(root, "tag_", "")),
                )
            )
        except Exception:  # noqa: BLE001
            logger.exception("missing_predicate: skip sentence at parse error")
            continue

    return hits


__all__ = [
    "MissingPredicateHit",
    "detect_missing_predicates",
    "has_finite_predicate",
    "sentence_has_finite_predicate",
]
