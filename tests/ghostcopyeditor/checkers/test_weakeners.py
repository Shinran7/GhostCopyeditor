"""Tests for density-gated weakener notes."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostcopyeditor.checkers.weakeners import WeakenerChecker, _hits, _outside_quotes
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import Category
from ghostcopyeditor.models.report import partition_action_list
from ghostcopyeditor.nlp.sentences import Sentence, clear_cache

WEAK = (
    "She was very tired. He felt rather cold. The road was just long. "
    "She saw the ship. The Captain watched it go.\n\n"
    '"Go," she said quietly. "Now," he said only. Softly said nothing here.\n\n'
    "---\n\n"
    "Rain fell on the roofs all night and into the grey morning.\n"
)


@pytest.fixture(autouse=True)
def _fresh() -> None:
    clear_cache()
    yield
    clear_cache()


def _check(text: str, **cfg: object) -> list:
    ch = Chapter(title="t", content=text, chapter_number=1, source_path=Path("c.md"))
    return WeakenerChecker().check(ch, GhostCopyeditorConfig(**cfg))


def _sent(text: str, dialogue: bool) -> Sentence:
    return Sentence(10, 10 + len(text), 1, dialogue, text)


def test_hits_narration() -> None:
    hits = _hits(_sent("She was very tired and he saw it. The ship seemed far.", False))
    rules = [(r, w) for r, _, _, w in hits]
    assert ("weak.qualifier", "very") in rules
    assert ("weak.filter_word", "saw") in rules
    assert not any(w == "seemed" for _, w in rules)  # "The" is not a subject name
    start, end = hits[0][1], hits[0][2]
    assert end - start == len("very")
    assert start == 10 + len("She was ")


def test_hits_dialogue_tags() -> None:
    hits = _hits(_sent('"Go," she said quietly, and he quietly answered. "very"', True))
    words = [w for r, _, _, w in hits]
    assert words == ["quietly", "quietly"]
    assert all(r == "weak.tag_adverb" for r, _, _, _ in hits)
    assert _hits(_sent('"x," he said only.', True)) == []


def test_outside_quotes() -> None:
    assert _outside_quotes('a "b" c') == [(0, 2), (5, 7)]
    assert _outside_quotes('"b"') == []


def test_density_gate() -> None:
    findings = _check(WEAK, weak_min_scene_words=1)
    rules = {f.rule_id for f in findings}
    assert rules == {"weak.qualifier", "weak.filter_word", "weak.tag_adverb"}
    assert all(f.metadata["scene"] == 1 for f in findings)
    assert all(f.category == Category.WEAKENER for f in findings)
    action, may_look = partition_action_list(findings)
    assert action == []
    assert len(may_look) == len(findings)


def test_under_limit_and_small_scene() -> None:
    assert _check(WEAK, weak_min_scene_words=1, weak_qualifier_per_1000=1000,
                  weak_filter_per_1000=1000, weak_tag_adverb_per_1000=1000) == []
    assert _check(WEAK) == []  # scenes below the 300-word floor


def test_disabled() -> None:
    assert _check(WEAK, weakeners_enabled=False, weak_min_scene_words=1) == []
