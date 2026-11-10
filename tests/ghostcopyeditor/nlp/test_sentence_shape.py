"""Tests for sentence shape and scene variety numbers."""

from __future__ import annotations

import pytest

import ghostcopyeditor.nlp.sentences as sent_mod
from ghostcopyeditor.nlp.sentence_shape import (
    SentenceShape,
    narration_shapes,
    scene_metrics,
    sentence_shape,
)
from ghostcopyeditor.nlp.sentences import Sentence, clear_cache, prose_sentences


@pytest.fixture(autouse=True)
def _fresh() -> None:
    clear_cache()
    yield
    clear_cache()


def _needs_nlp() -> None:
    if sent_mod.get_nlp() is None:
        pytest.skip("spaCy model not installed")


def _one(text: str) -> SentenceShape:
    return narration_shapes(prose_sentences(text))[0]


class TestShape:
    def test_subject_first_plain(self) -> None:
        _needs_nlp()
        s = _one("She opened the door.")
        assert s.subject_first is True
        assert s.clauses == 1
        assert s.opener == "she"
        assert s.opener_kind == "subject"
        assert s.words == 4

    def test_fronted_clause(self) -> None:
        _needs_nlp()
        s = _one("When the rain stopped, she opened the door and walked out.")
        assert s.subject_first is False
        assert s.clauses >= 2
        assert s.opener_kind == "subordinate"

    @pytest.mark.parametrize(
        ("text", "kind"),
        [
            ("Slowly the old man rose.", "adverb"),
            ("Under the bridge the water ran cold.", "preposition"),
            ("Running hard, she reached the gate.", "verb"),
            ("And then it ended.", "conjunction"),
            ("Yes.", "other"),
        ],
    )
    def test_opener_kinds(self, text: str, kind: str) -> None:
        _needs_nlp()
        assert _one(text).opener_kind == kind

    def test_no_verb_root(self) -> None:
        _needs_nlp()
        assert _one("A long night of rain.").subject_first is False

    def test_no_subject(self) -> None:
        _needs_nlp()
        assert _one("Go home now.").subject_first is False

    def test_fallback_no_span(self) -> None:
        s = sentence_shape(Sentence(0, 9, 1, False, "Rain fell"))
        assert s.subject_first is None
        assert s.clauses is None
        assert s.opener_kind == "unknown"
        empty = sentence_shape(Sentence(0, 3, 1, False, "..."))
        assert empty.opener == ""

    def test_punct_only_span(self) -> None:
        _needs_nlp()
        nlp = sent_mod.get_nlp()
        span = nlp("...")[0:1]
        s = sentence_shape(Sentence(0, 3, 1, False, "...", span))
        assert s.opener_kind == "other"
        assert s.subject_first is False

    def test_dialogue_skipped(self) -> None:
        sents = prose_sentences('"Hi," she said. He left.', use_nlp=False)
        assert [s.opener for s in narration_shapes(sents)] == ["he"]


class TestMetrics:
    def test_empty(self) -> None:
        assert scene_metrics([])["variety"] is None

    def test_flat_vs_varied(self) -> None:
        _needs_nlp()
        flat = " ".join(["She walked in. She sat down. She looked up."] * 5)
        varied = (
            "When the rain finally stopped, the hauler crews drifted back "
            "toward the ridge where the old pylons stood. Nobody spoke. "
            "Under the second pylon, half buried in grit, lay a sensor that "
            "had not reported in a decade, and Mara knelt beside it. Was it "
            "still warm? Its casing, scored by years of wind, gave under her "
            "thumb."
        )
        f = scene_metrics(narration_shapes(prose_sentences(flat)))
        v = scene_metrics(narration_shapes(prose_sentences(varied)))
        assert f["top_opener"] == "she"
        assert f["variety"] < v["variety"]
        assert f["subject_first_share"] > v["subject_first_share"]

    def test_fallback_metrics(self) -> None:
        shapes = narration_shapes(prose_sentences("Rain fell. Wind rose.", use_nlp=False))
        m = scene_metrics(shapes)
        assert m["subject_first_share"] is None
        assert m["multi_clause_share"] is None
        assert 0 <= m["variety"] <= 100

    def test_zero_word_sentences(self) -> None:
        shapes = [SentenceShape(0, 1, 1, 0, "", "other", None, None)]
        m = scene_metrics(shapes)
        assert m["length_spread"] == 0.0
        assert m["top_opener"] == ""
