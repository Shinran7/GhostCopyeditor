"""Weakener notes: qualifiers, filter words, and adverbs on dialogue tags.

One "very" is fine. A scene full of them is not. Hits are counted per scene
per 1,000 words; a hit becomes a finding only when its scene is over the
limit for that rule. Report-only.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING, ClassVar

from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Severity,
    location_from_span,
)

if TYPE_CHECKING:
    from ghostcopyeditor.nlp.sentences import Sentence

_WORD_RE = re.compile(r"[A-Za-z0-9']+")

_QUALIFIER_RE = re.compile(
    r"\b(?:very|really|quite|rather|somewhat|slightly|fairly|pretty much|"
    r"a (?:bit|little)|kind of|sort of|just|almost|nearly|barely)\b",
    re.IGNORECASE,
)
# "pretty" and "a little" also work as plain words ("a pretty face", "a little
# boat"); only count them before an adjective-like word ending a phrase.
_FILTER_RE = re.compile(
    r"\b(?P<who>he|she|they|i|we|you|[A-Z][a-z]+)\s+(?:could\s+)?"
    r"(?P<verb>saw|see|heard|hear|felt|feel|noticed|watched|realized|realised|"
    r"wondered|seemed|smelled|smelt|sensed)\b"
)
_TAG_VERBS = (
    r"said|asked|replied|whispered|muttered|murmured|shouted|called|answered|"
    r"snapped|added|told|says|asks"
)
_TAG_ADVERB_RE = re.compile(
    rf"\b(?:{_TAG_VERBS})\s+(?P<adv>[a-z]+ly)\b|\b(?P<adv2>[a-z]+ly)\s+(?:{_TAG_VERBS})\b",
    re.IGNORECASE,
)
_NOT_ADVERBS = frozenset(
    {
        "only", "early", "likely", "family", "holy", "ugly", "lonely", "friendly",
        "daily", "belly", "rely", "reply", "supply", "apply", "fly", "july",
        "italy", "ally", "bully", "jelly", "silly", "lovely", "elderly", "orderly",
        "hourly", "weekly", "monthly", "yearly", "nightly", "costly", "deadly",
        "lively", "chilly", "curly", "surly", "burly", "sly", "wily", "oily",
    }
)
_QUOTED_RE = re.compile(r"\"[^\"]*\"|“[^”]*”")
_NOT_NAMES = frozenset(
    {"The", "A", "An", "It", "This", "That", "Then", "When", "There", "But", "And"}
)

_MESSAGES = {
    "weak.qualifier": "Qualifier “{word}” softens the line.",
    "weak.filter_word": "Filter word “{word}” puts the reader one step back.",
    "weak.tag_adverb": "Adverb “{word}” on a dialogue tag; let the line carry it.",
}


def _outside_quotes(text: str) -> list[tuple[int, int]]:
    """Spans of *text* outside quoted speech."""
    out: list[tuple[int, int]] = []
    cursor = 0
    for match in _QUOTED_RE.finditer(text):
        if match.start() > cursor:
            out.append((cursor, match.start()))
        cursor = match.end()
    if cursor < len(text):
        out.append((cursor, len(text)))
    return out


def _hits(sentence: Sentence) -> list[tuple[str, int, int, str]]:
    """(rule, start, end, word) hits with chapter offsets."""
    out: list[tuple[str, int, int, str]] = []
    base = sentence.start
    text = sentence.text
    if not sentence.dialogue:
        for match in _QUALIFIER_RE.finditer(text):
            out.append(("weak.qualifier", base + match.start(), base + match.end(), match.group(0)))
        for match in _FILTER_RE.finditer(text):
            if match.group("who") in _NOT_NAMES:
                continue
            start, end = match.span("verb")
            out.append(("weak.filter_word", base + start, base + end, match.group("verb")))
        return out
    for seg_start, seg_end in _outside_quotes(text):
        for match in _TAG_ADVERB_RE.finditer(text, seg_start, seg_end):
            group = "adv" if match.group("adv") else "adv2"
            word = match.group(group)
            if word.lower() in _NOT_ADVERBS:
                continue
            start, end = match.span(group)
            out.append(("weak.tag_adverb", base + start, base + end, word))
    return out


class WeakenerChecker:
    """Density-gated weakener notes."""

    rule_ids: ClassVar[tuple[str, ...]] = (
        "weak.qualifier",
        "weak.filter_word",
        "weak.tag_adverb",
    )

    def check(self, chapter: Chapter, cfg: GhostCopyeditorConfig) -> list[Finding]:
        if not cfg.weakeners_enabled:
            return []
        # Imported here: nlp.sentences imports checkers.regions (import cycle).
        from ghostcopyeditor.nlp.sentences import prose_sentences

        limits = {
            "weak.qualifier": cfg.weak_qualifier_per_1000,
            "weak.filter_word": cfg.weak_filter_per_1000,
            "weak.tag_adverb": cfg.weak_tag_adverb_per_1000,
        }
        words: dict[int, int] = defaultdict(int)
        hits: dict[tuple[int, str], list[tuple[int, int, str]]] = defaultdict(list)
        for sentence in prose_sentences(chapter.content):
            words[sentence.scene] += len(_WORD_RE.findall(sentence.text))
            for rule, start, end, word in _hits(sentence):
                hits[(sentence.scene, rule)].append((start, end, word))

        findings: list[Finding] = []
        for (scene, rule), rows in sorted(hits.items()):
            scene_words = words[scene]
            if scene_words < cfg.weak_min_scene_words:
                continue
            rate = 1000 * len(rows) / scene_words
            limit = limits[rule]
            if rate <= limit:
                continue
            for start, end, word in rows:
                findings.append(
                    Finding(
                        id="",
                        category=Category.WEAKENER,
                        severity=Severity.SUGGESTION,
                        message=(
                            _MESSAGES[rule].format(word=word)
                            + f" Scene {scene}: {rate:.1f} per 1,000 words (limit {limit:g})."
                        ),
                        location=location_from_span(chapter, start, end),
                        engine=Engine.DETERMINISTIC,
                        suggestion="(cut or replace with something concrete)",
                        rule_id=rule,
                        applyable=False,
                        metadata={
                            "scene": scene,
                            "word": word.lower(),
                            "scene_rate_per_1000": round(rate, 1),
                            "limit_per_1000": limit,
                            "scene_count": len(rows),
                        },
                    )
                )
        return findings


__all__ = ["WeakenerChecker"]
