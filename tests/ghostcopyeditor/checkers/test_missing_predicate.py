"""Tests for MissingPredicateChecker + skip warning wiring."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ghostcopyeditor.checkers.missing_predicate import MissingPredicateChecker
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.nlp import get_nlp, missing_predicate_skip_warning
from ghostcopyeditor.nlp.spacy_runtime import _reset_for_tests

RESONANCE = (
    "A rough chatter through Kieran's palm as he lifted the hauler "
    "clear of the buttress."
)


def _chapter(text: str, *, num: int = 1) -> Chapter:
    return Chapter(
        title="T",
        content=text,
        chapter_number=num,
        source_path=Path(f"/story/chapters/chapter-{num:03d}.md"),
    )


@pytest.fixture(autouse=True)
def _fresh_nlp() -> None:
    _reset_for_tests()
    yield
    _reset_for_tests()


def _model_available() -> bool:
    _reset_for_tests()
    ready = get_nlp() is not None
    _reset_for_tests()
    return ready


@pytest.mark.skipif(not _model_available(), reason="spaCy en_core_web_sm not installed")
class TestMissingPredicateChecker:
    def test_resonance_finding_shape(self) -> None:
        findings = MissingPredicateChecker().check(
            _chapter(RESONANCE), GhostCopyeditorConfig()
        )
        hits = [f for f in findings if f.rule_id == "mech.missing_predicate"]
        assert len(hits) >= 1
        hit = hits[0]
        assert hit.category.value == "grammar"
        assert hit.severity.value == "warning"
        assert hit.engine.value == "deterministic"
        assert hit.applyable is False
        assert hit.replacement is None
        assert hit.suggestion is None
        assert "expected_old" not in hit.metadata
        assert hit.metadata["root_text"] == "chatter"
        assert hit.metadata["root_pos"] == "NOUN"
        assert hit.metadata["root_tag"] == "NN"

    def test_flag_off_silent(self) -> None:
        cfg = GhostCopyeditorConfig(missing_predicate_enabled=False)
        assert MissingPredicateChecker().check(_chapter(RESONANCE), cfg) == []

    def test_passes_config_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import ghostcopyeditor.checkers.missing_predicate as mod

        captured: dict = {}

        def _fake(text: str, **kwargs: object) -> list:
            captured.update(kwargs)
            return []

        monkeypatch.setattr(mod, "detect_missing_predicates", _fake)
        cfg = GhostCopyeditorConfig(
            missing_predicate_min_tokens=7,
            missing_predicate_skip_dialogue_heavy=False,
            missing_predicate_require_period=False,
        )
        MissingPredicateChecker().check(_chapter(RESONANCE), cfg)
        assert captured["min_tokens"] == 7
        assert captured["skip_dialogue_heavy"] is False
        assert captured["require_period"] is False
        assert captured["non_prose"] is None


def test_skip_warning_string_stable() -> None:
    warn = missing_predicate_skip_warning(
        SimpleNamespace(missing_predicate_enabled=True)
    )
    # When model present, warning is None; force unavailable for assert.
    import ghostcopyeditor.nlp.spacy_runtime as rt

    _reset_for_tests()
    rt._LOAD_ERROR = "forced"
    rt._NLP = None
    warn = missing_predicate_skip_warning(
        SimpleNamespace(missing_predicate_enabled=True)
    )
    assert warn == (
        "missing_predicate skipped: install ghostcopyeditor[nlp] and run: "
        "python -m spacy download en_core_web_sm"
    )
