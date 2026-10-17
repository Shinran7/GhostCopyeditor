"""Tests for shared missing-predicate detector (spaCy optional)."""

from __future__ import annotations

import pytest

from ghostcopyeditor.nlp import (
    detect_missing_predicates,
    get_nlp,
    nlp_unavailable_reason,
)
from ghostcopyeditor.nlp.spacy_runtime import _reset_for_tests

# Resonance Ch4 opener: ROOT chatter / NOUN / NN on en_core_web_sm 3.8.0.
# Subordinate "lifted" is advcl/VBD — not a finite aux child.
RESONANCE = (
    "A rough chatter through Kieran's palm as he lifted the hauler "
    "clear of the buttress."
)


@pytest.fixture(autouse=True)
def _fresh_nlp_singleton() -> None:
    _reset_for_tests()
    yield
    _reset_for_tests()


@pytest.fixture(scope="module")
def nlp_ready() -> bool:
    _reset_for_tests()
    return get_nlp() is not None


class TestSoftSkipWithoutModel:
    def test_detect_empty_when_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import ghostcopyeditor.nlp.missing_predicate as mp

        monkeypatch.setattr(mp, "get_nlp", lambda: None)
        assert detect_missing_predicates(RESONANCE) == []

    def test_unavailable_reason_set_after_failed_load(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ghostcopyeditor.nlp.spacy_runtime as rt

        monkeypatch.setattr(rt, "_NLP", None)
        monkeypatch.setattr(rt, "_LOAD_ERROR", None)

        def _fail_load(*_a: object, **_k: object) -> None:
            raise OSError("[E050] Can't find model")

        fake_spacy = type("S", (), {"load": staticmethod(_fail_load)})()
        monkeypatch.setitem(__import__("sys").modules, "spacy", fake_spacy)
        reason = nlp_unavailable_reason()
        assert reason is not None
        assert "E050" in reason or "Can't find" in reason


def _model_available() -> bool:
    _reset_for_tests()
    ready = get_nlp() is not None
    _reset_for_tests()
    return ready


@pytest.mark.skipif(not _model_available(), reason="spaCy en_core_web_sm not installed")
class TestWithModel:
    def test_resonance_loud_with_recorded_root(self) -> None:
        assert get_nlp() is not None
        hits = detect_missing_predicates(RESONANCE)
        assert len(hits) >= 1
        hit = hits[0]
        assert "chatter" in hit.excerpt
        # Recorded on en_core_web_sm 3.8.0: chatter / NOUN / NN
        assert hit.root_text == "chatter"
        assert hit.root_pos == "NOUN"
        assert hit.root_tag == "NN"
        assert hit.start == 0
        assert hit.end > hit.start

    def test_finite_verb_quiet(self) -> None:
        text = (
            "A rough chatter ran through Kieran's palm as he lifted the hauler."
        )
        assert detect_missing_predicates(text) == []

    def test_passive_quiet(self) -> None:
        assert detect_missing_predicates(
            "The hauler was lifted clear of the buttress."
        ) == []

    def test_perfect_quiet(self) -> None:
        assert detect_missing_predicates("Kieran has lifted the hauler.") == []

    def test_perfect_passive_quiet(self) -> None:
        assert detect_missing_predicates("The hauler has been lifted.") == []

    def test_copula_quiet(self) -> None:
        assert detect_missing_predicates("Kieran is ready.") == []

    def test_imperative_quiet(self) -> None:
        assert detect_missing_predicates(
            "Lift the hauler clear of the buttress."
        ) == []

    def test_bare_vbg_loud(self) -> None:
        # Design example is short; pad to min_tokens=5 alphabetic tokens.
        hits = detect_missing_predicates("Running through the dark corridor.")
        assert len(hits) >= 1
        assert hits[0].root_tag == "VBG"

    def test_bare_vbn_loud(self) -> None:
        hits = detect_missing_predicates("Finished with the long haul.")
        assert len(hits) >= 1
        assert hits[0].root_tag == "VBN"

    def test_dialogue_heavy_quiet(self) -> None:
        assert detect_missing_predicates('"Not tonight."') == []

    def test_short_quiet(self) -> None:
        assert detect_missing_predicates("Yes.") == []

    def test_frontmatter_and_heading_quiet(self) -> None:
        # Prior quiet sentence lets spaCy split prose from glued header.
        text = (
            "---\n"
            "title: Sample\n"
            "---\n"
            "\n"
            "# Opening Scene\n"
            "\n"
            "He waited.\n"
            "\n"
            f"{RESONANCE}\n"
        )
        hits = detect_missing_predicates(text)
        assert len(hits) >= 1
        hit = hits[0]
        assert text[hit.start : hit.end].strip().startswith("A rough chatter")
        for h in hits:
            assert not text[h.start : h.end].lstrip().startswith("#")
            assert "title:" not in text[h.start : h.end]

    def test_question_not_loud_under_period_gate(self) -> None:
        text = "A rough chatter through Kieran's palm as he lifted the hauler?"
        assert detect_missing_predicates(text) == []

    def test_ellipsis_soft_voice_skip(self) -> None:
        assert detect_missing_predicates("Waiting in the dark alone…") == []

    def test_require_period_false_allows_question(self) -> None:
        text = "Running through the dark corridor?"
        hits = detect_missing_predicates(text, require_period=False)
        assert len(hits) >= 1
