"""Per-sentence shape and per-scene variety numbers (syntactic monotony).

LLM prose tends to run short, same-shaped sentences: subject, verb, object,
stop, again and again. This module measures that. It reports; it fixes nothing.

Shape needs spaCy. Without it, length and opener word still work, and the
subject-first and clause numbers are left as ``None``.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Any

from ghostcopyeditor.nlp.sentences import Sentence

_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_SUBJ_DEPS = frozenset({"nsubj", "nsubjpass", "expl", "csubj"})
_CLAUSE_DEPS = frozenset({"advcl", "ccomp", "relcl", "acl", "csubj"})
_SUBJECT_GAP = 3  # main verb within this many tokens after the subject ends

# Variety score targets: a scene that reaches all of these scores 100.
_TARGET_SPREAD = 0.55
_TARGET_MULTI = 0.45
_TARGET_MEAN_LEN = 16.0


@dataclass(frozen=True)
class SentenceShape:
    """Shape of one narration sentence."""

    start: int
    end: int
    scene: int
    words: int
    opener: str
    opener_kind: str
    subject_first: bool | None
    clauses: int | None


def _opener_kind(tok: Any) -> str:
    if tok.dep_ in _SUBJ_DEPS or tok.head.dep_ in _SUBJ_DEPS:
        return "subject"
    if tok.pos_ in {"ADV"}:
        return "adverb"
    if tok.pos_ == "ADP" or tok.dep_ == "prep":
        return "preposition"
    if tok.pos_ in {"VERB", "AUX"}:
        return "verb"
    if tok.pos_ == "SCONJ" or tok.dep_ == "mark":
        return "subordinate"
    if tok.pos_ == "CCONJ":
        return "conjunction"
    return "other"


def _subject_first(span: Any) -> bool:
    root = span.root
    if root.pos_ not in {"VERB", "AUX"}:
        return False
    subjects = [t for t in root.children if t.dep_ in _SUBJ_DEPS]
    if not subjects:
        return False
    subj = subjects[0]
    words = [t for t in span if not t.is_punct and not t.is_space]
    if not words or subj.left_edge.i != words[0].i:
        return False
    gap: int = root.i - subj.right_edge.i
    return 0 <= gap <= _SUBJECT_GAP


def _clauses(span: Any) -> int:
    count = 1
    for tok in span:
        if tok.dep_ in _CLAUSE_DEPS or tok.dep_ == "conj" and tok.pos_ in {"VERB", "AUX"}:
            count += 1
    return count


def sentence_shape(sentence: Sentence) -> SentenceShape:
    """Measure one sentence."""
    words = _WORD_RE.findall(sentence.text)
    opener = words[0].lower() if words else ""
    span = sentence.span
    if span is None:
        return SentenceShape(
            sentence.start, sentence.end, sentence.scene, len(words), opener,
            "unknown", None, None,
        )
    first = next((t for t in span if not t.is_punct and not t.is_space), None)
    kind = _opener_kind(first) if first is not None else "other"
    return SentenceShape(
        sentence.start, sentence.end, sentence.scene, len(words), opener, kind,
        _subject_first(span), _clauses(span),
    )


def narration_shapes(sentences: list[Sentence]) -> list[SentenceShape]:
    """Shapes for narration sentences (dialogue skipped)."""
    return [sentence_shape(s) for s in sentences if not s.dialogue]


def _share(flags: list[bool]) -> float:
    return sum(flags) / len(flags) if flags else 0.0


def scene_metrics(shapes: list[SentenceShape]) -> dict[str, Any]:
    """Variety numbers for one scene's narration sentences.

    ``variety`` runs 0–100; higher means more varied sentences.
    """
    if not shapes:
        return {"narration_words_mean": 0.0, "variety": None}
    lengths = [s.words for s in shapes]
    mean = statistics.fmean(lengths)
    spread = statistics.pstdev(lengths) / mean if mean else 0.0
    openers = Counter(s.opener for s in shapes if s.opener)
    top_word, top_count = openers.most_common(1)[0] if openers else ("", 0)
    top_share = top_count / len(shapes)
    parsed = [s for s in shapes if s.subject_first is not None]
    subj_share = _share([bool(s.subject_first) for s in parsed]) if parsed else None
    multi_share = _share([(s.clauses or 1) > 1 for s in parsed]) if parsed else None

    parts = [
        min(spread / _TARGET_SPREAD, 1.0),
        min(mean / _TARGET_MEAN_LEN, 1.0),
        1.0 - min(max(top_share - 0.1, 0.0) / 0.3, 1.0),
    ]
    if subj_share is not None and multi_share is not None:
        parts.append(1.0 - min(max(subj_share - 0.4, 0.0) / 0.4, 1.0))
        parts.append(min(multi_share / _TARGET_MULTI, 1.0))
    return {
        "narration_words_mean": round(mean, 1),
        "length_spread": round(spread, 2),
        "top_opener": top_word,
        "top_opener_share": round(top_share, 2),
        "subject_first_share": None if subj_share is None else round(subj_share, 2),
        "multi_clause_share": None if multi_share is None else round(multi_share, 2),
        "variety": round(100 * statistics.fmean(parts)),
    }


__all__ = [
    "SentenceShape",
    "narration_shapes",
    "scene_metrics",
    "sentence_shape",
]
