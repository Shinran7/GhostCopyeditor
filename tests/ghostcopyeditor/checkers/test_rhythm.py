"""Tests for rhythm (syntactic monotony) notes."""

from __future__ import annotations

from pathlib import Path

import pytest

import ghostcopyeditor.nlp.sentences as sent_mod
from ghostcopyeditor.checkers.rhythm import RhythmChecker, _excerpt, _pct, _runs
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import Category
from ghostcopyeditor.models.report import partition_action_list
from ghostcopyeditor.nlp.sentence_shape import SentenceShape
from ghostcopyeditor.nlp.sentences import clear_cache

FLAT = (
    "She walked in. She sat down. She looked up. She waited.\n\n"
    "He came back. He took the cup. He drank it. He left.\n"
)


@pytest.fixture(autouse=True)
def _fresh() -> None:
    clear_cache()
    yield
    clear_cache()


def _check(text: str, **cfg: object) -> list:
    ch = Chapter(title="t", content=text, chapter_number=1, source_path=Path("c.md"))
    return RhythmChecker().check(ch, GhostCopyeditorConfig(**cfg))


def _needs_nlp() -> None:
    if sent_mod.get_nlp() is None:
        pytest.skip("spaCy model not installed")


def _shape(scene: int, opener: str) -> SentenceShape:
    return SentenceShape(0, 1, scene, 3, opener, "subject", True, 1)


def test_runs_break_on_none_and_scene() -> None:
    items = [_shape(1, "a"), _shape(1, "a"), None, _shape(1, "a"), _shape(2, "a")]
    assert _runs(items, lambda s: s.opener, 2) == [items[:2]]
    assert _runs(items, lambda s: None, 1) == []


def test_opener_and_shape_runs() -> None:
    _needs_nlp()
    findings = _check(FLAT, rhythm_min_scene_sentences=100)
    rules = [f.rule_id for f in findings]
    assert rules.count("rhythm.same_opener_run") == 2
    assert "rhythm.shape_run" in rules
    opener = next(f for f in findings if f.rule_id == "rhythm.same_opener_run")
    assert opener.metadata["opener"] == "she"
    assert opener.metadata["sentences"] == 4
    assert all(f.category == Category.RHYTHM and not f.applyable for f in findings)
    action, may_look = partition_action_list(findings)
    assert action == []
    assert len(may_look) == len(findings)


def test_dialogue_breaks_runs() -> None:
    text = 'She walked in. She sat down. "Hi," she said. She looked up.\n'
    assert not [f for f in _check(text) if f.rule_id == "rhythm.same_opener_run"]


def test_flat_scene() -> None:
    _needs_nlp()
    text = " ".join(["She walked in. He sat down. It got late."] * 8)
    findings = _check(text, rhythm_min_scene_sentences=20, rhythm_flat_variety=90)
    flat = [f for f in findings if f.rule_id == "rhythm.flat_scene"]
    assert len(flat) == 1
    assert flat[0].metadata["scene"] == 1
    assert "variety" in flat[0].message


def test_flat_scene_thresholds() -> None:
    text = " ".join(["She walked in. He sat down. It got late."] * 8)
    assert not [
        f for f in _check(text, rhythm_flat_variety=0) if f.rule_id == "rhythm.flat_scene"
    ]
    assert not [
        f
        for f in _check(text, rhythm_min_scene_sentences=500)
        if f.rule_id == "rhythm.flat_scene"
    ]


def test_disabled() -> None:
    assert _check(FLAT, rhythm_enabled=False) == []


def test_helpers() -> None:
    assert _excerpt("a  b") == "a b"
    long = _excerpt("word " * 100)
    assert len(long) == 160
    assert long.endswith("…")
    assert _pct(0.5) == "50%"
    assert _pct(None) == "n/a"
