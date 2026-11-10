"""Hollow-imagery candidates: lines that may sound literary but mean nothing.

LLM drafts often end a sentence on a decorative tag ("a smell with no
opinion"), give objects a mind ("the archive considered it"), or let a
sound be "filled". Code finds the candidates; an LLM judge decides
(``llm_engine/hollow.py``). Candidates alone are not findings: the broad
patterns match plenty of good prose.

Calibration (40 Autonomicon chapters vs. two public-domain novels):
tail tags run 3.1 vs. 0.9 per 1,000 narration words; object-with-a-mind
subjects 0.8 vs. 0.2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ", a/an/the/its … ." closing a sentence: the appositive tag.
_TAIL_RE = re.compile(r",\s+(?:an?|the|one|its|their)\s+[^,.;!?\"“”]{3,60}[.;]\s*$")
# Narrow shapes that are nearly always decoration in these drafts.
_NARROW_RE = re.compile(
    r"\b\w+'s\s+(?:idea|version|notion)\s+of\b"
    r"|\bused\s+the\s+\w+\s+to\s+(?:become|turn|grow)\b"
    r"|\b(?:filled|answered|met)\s+the\s+(?:silence|quiet|hush|knock|pause|gap)\b"
    r"|,\s+an?\s+\w+\s+(?:rather\s+than|with\s+no|without)\s",
    re.IGNORECASE,
)
# Verbs of mind or will; an inanimate noun as their subject is a candidate.
_MIND_VERBS = frozenset(
    {
        "decide", "want", "know", "refuse", "consider", "remember", "forgive",
        "agree", "insist", "wait", "listen", "watch", "believe", "hope", "care",
        "mind", "prefer", "expect", "trust", "doubt", "admit", "pretend",
        "judge", "forget", "notice", "wonder", "intend", "hesitate", "argue",
        "accept", "ask", "answer", "have",
    }
)
# "have" only counts with a mind-like object ("the door had opinions").
_HAVE_OBJECTS = frozenset(
    {
        "opinion", "manner", "patience", "memory", "mood", "temper", "sense",
        "appetite", "intention", "idea", "conscience", "preference",
    }
)
_PEOPLE = frozenset(
    {
        "man", "woman", "people", "person", "crew", "girl", "boy", "child",
        "mother", "father", "officer", "captain", "guard", "pilot", "delegate",
        "sergeant", "clerk", "soldier", "doctor", "stranger", "friend", "dog",
        "wolf", "horse", "cat", "bird",
    }
)


@dataclass(frozen=True)
class HollowCandidate:
    """One sentence worth asking the judge about. ``end`` is exclusive."""

    start: int
    end: int
    text: str
    pattern: str  # "narrow" | "tail" | "mind"


def _mind_subject(span: object) -> bool:
    root = getattr(span, "root", None)
    if root is None or root.lemma_ not in _MIND_VERBS:
        return False
    subjects = [c for c in root.children if c.dep_ == "nsubj"]
    if not any(s.pos_ == "NOUN" and s.lemma_.lower() not in _PEOPLE for s in subjects):
        return False
    if root.lemma_ == "have":
        objects = [c for c in root.children if c.dep_ == "dobj"]
        return bool(objects) and objects[0].lemma_.lower() in _HAVE_OBJECTS
    return True


def hollow_candidates(text: str) -> list[HollowCandidate]:
    """Narration sentences in *text* that match a hollow-imagery shape."""
    from ghostcopyeditor.nlp.sentences import prose_sentences

    out: list[HollowCandidate] = []
    for sentence in prose_sentences(text):
        if sentence.dialogue:
            continue
        flat = " ".join(sentence.text.split())
        if _NARROW_RE.search(flat):
            pattern = "narrow"
        elif _TAIL_RE.search(flat):
            pattern = "tail"
        elif sentence.span is not None and _mind_subject(sentence.span):
            pattern = "mind"
        else:
            continue
        out.append(HollowCandidate(sentence.start, sentence.end, sentence.text, pattern))
    return out


__all__ = ["HollowCandidate", "hollow_candidates"]
