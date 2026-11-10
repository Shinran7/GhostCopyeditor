"""Fill scene number and sentence span on findings; build per-scene profiles."""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from ghostcopyeditor.checkers.regions import scene_number_at, scene_spans
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import Finding
from ghostcopyeditor.nlp.sentences import prose_sentences, sentence_index_at

_WORD_RE = re.compile(r"[A-Za-z0-9']+")


def annotate_positions(findings: list[Finding], chapter: Chapter) -> list[Finding]:
    """Set ``location.scene`` and the sentence span for findings with offsets."""
    text = chapter.content
    scenes = scene_spans(text)
    sentences = prose_sentences(text)
    for finding in findings:
        loc = finding.location
        if loc.char_start is None or loc.char_end is None:
            continue
        first = sentence_index_at(sentences, loc.char_start)
        last = sentence_index_at(sentences, max(loc.char_end - 1, loc.char_start))
        sent_start = sentences[first].start if first is not None else None
        if last is not None:
            sent_end: int | None = sentences[last].end
        elif first is not None:
            sent_end = sentences[first].end
        else:
            sent_end = None
        finding.location = dataclasses.replace(
            loc,
            scene=loc.scene or scene_number_at(loc.char_start, scenes),
            sentence_start=sent_start if loc.sentence_start is None else loc.sentence_start,
            sentence_end=sent_end if loc.sentence_end is None else loc.sentence_end,
        )
    return findings


def scene_profiles(chapter: Chapter) -> list[dict[str, Any]]:
    """Basic per-scene counts. Rhythm and weakener checks add their numbers."""
    text = chapter.content
    sentences = prose_sentences(text)
    out: list[dict[str, Any]] = []
    for number, span in enumerate(scene_spans(text), start=1):
        in_scene = [s for s in sentences if s.scene == number]
        out.append(
            {
                "scene": number,
                "char_start": span.start,
                "char_end": span.end,
                "words": sum(len(_WORD_RE.findall(s.text)) for s in in_scene),
                "sentences": len(in_scene),
                "narration_sentences": sum(1 for s in in_scene if not s.dialogue),
            }
        )
    return out


__all__ = ["annotate_positions", "scene_profiles"]
