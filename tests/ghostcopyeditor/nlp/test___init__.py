"""Smoke import for ghostcopyeditor.nlp public API."""

from __future__ import annotations

from ghostcopyeditor import nlp


def test_public_exports() -> None:
    assert callable(nlp.detect_missing_predicates)
    assert callable(nlp.get_nlp)
    assert callable(nlp.nlp_unavailable_reason)
    assert callable(nlp.missing_predicate_skip_warning)
    assert nlp.MissingPredicateHit is not None
