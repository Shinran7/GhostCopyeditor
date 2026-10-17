"""Tests for spaCy load-once runtime helpers."""

from __future__ import annotations

import io

import pytest

from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.nlp.spacy_runtime import (
    _reset_for_tests,
    get_nlp,
    missing_predicate_skip_warning,
    nlp_unavailable_reason,
    warn_stderr_once,
)


@pytest.fixture(autouse=True)
def _fresh() -> None:
    _reset_for_tests()
    yield
    _reset_for_tests()


def test_get_nlp_returns_pipeline_or_none() -> None:
    nlp = get_nlp()
    # Soft path: either pipeline or recorded error.
    if nlp is None:
        assert nlp_unavailable_reason() is not None
    else:
        assert nlp_unavailable_reason() is None
        assert get_nlp() is nlp  # singleton


def test_skip_warning_when_enabled_and_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ghostcopyeditor.nlp.spacy_runtime as rt

    monkeypatch.setattr(rt, "_LOAD_ERROR", "missing model")
    monkeypatch.setattr(rt, "_NLP", None)
    cfg = GhostCopyeditorConfig()
    # Config field lands in Slice 2; getattr default True until then.
    warn = missing_predicate_skip_warning(cfg)
    assert warn is not None
    assert "en_core_web_sm" in warn


def test_skip_warning_none_when_disabled() -> None:
    from types import SimpleNamespace

    warn = missing_predicate_skip_warning(
        SimpleNamespace(missing_predicate_enabled=False)
    )
    assert warn is None


def test_warn_stderr_once() -> None:
    buf = io.StringIO()
    warn_stderr_once(buf)
    warn_stderr_once(buf)
    text = buf.getvalue()
    assert text.count("missing_predicate skipped") == 1
