"""Tests for prose sentence splitting with scene numbers."""

from __future__ import annotations

import pytest

import ghostcopyeditor.nlp.sentences as sent_mod
from ghostcopyeditor.checkers.regions import Span, scene_number_at, scene_spans
from ghostcopyeditor.nlp.sentences import (
    clear_cache,
    prose_sentences,
    sentence_index_at,
)

TEXT = (
    "---\ntitle: x\n---\n\n"
    "She walked in. He sat down.\n\n"
    "# Heading\n\n"
    '"Hello there," she said. The door shut.\n\n'
    "---\n\n"
    "Rain fell all night.\r\n\r\nMorning came late.\n"
)


@pytest.fixture(autouse=True)
def _fresh() -> None:
    clear_cache()
    yield
    clear_cache()


@pytest.fixture(params=[True, False], ids=["spacy", "fallback"])
def use_nlp(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> bool:
    if not request.param:
        monkeypatch.setattr(sent_mod, "get_nlp", lambda: None)
    elif sent_mod.get_nlp() is None:
        pytest.skip("spaCy model not installed")
    return bool(request.param)


class TestScenes:
    def test_split_on_breaks_skips_frontmatter(self) -> None:
        scenes = scene_spans(TEXT)
        assert len(scenes) == 2
        assert TEXT[scenes[0].start : scenes[0].end].lstrip().startswith("She walked")
        assert "Rain fell" in TEXT[scenes[1].start : scenes[1].end]

    def test_no_break_is_one_scene(self) -> None:
        assert scene_spans("Just one.") == [Span(0, 9)]

    def test_empty_scenes_dropped(self) -> None:
        text = "---\n\nOnly scene.\n"
        assert len(scene_spans(text)) == 1

    def test_all_empty_keeps_one(self) -> None:
        assert len(scene_spans("")) == 1

    def test_scene_number_at(self) -> None:
        scenes = [Span(0, 5), Span(8, 12)]
        assert scene_number_at(2, scenes) == 1
        assert scene_number_at(9, scenes) == 2
        assert scene_number_at(6, scenes) is None


class TestSentences:
    def test_split_and_flags(self, use_nlp: bool) -> None:
        sents = prose_sentences(TEXT)
        texts = [s.text for s in sents]
        assert "She walked in." in texts
        assert "Rain fell all night." in texts
        assert not any("Heading" in t or "title" in t for t in texts)
        by_text = {s.text: s for s in sents}
        assert by_text["She walked in."].scene == 1
        assert by_text["Morning came late."].scene == 2
        assert any(s.dialogue for s in sents)
        assert not by_text["The door shut."].dialogue
        for s in sents:
            assert TEXT[s.start : s.end] == s.text
        if use_nlp:
            assert by_text["She walked in."].span is not None

    def test_trailing_text_without_period(self, use_nlp: bool) -> None:
        del use_nlp
        sents = prose_sentences("One here. Then no stop")
        assert sents[-1].text.endswith("no stop")

    def test_index_lookup(self) -> None:
        sents = prose_sentences("Alpha one. Beta two.", use_nlp=False)
        assert sentence_index_at(sents, 0) == 0
        assert sentence_index_at(sents, len("Alpha one. ") + 1) == 1
        assert sentence_index_at(sents, 10) is None
        assert sentence_index_at([], 0) is None
