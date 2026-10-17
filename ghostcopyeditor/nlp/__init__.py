"""Shared NLP helpers (optional spaCy)."""

from __future__ import annotations

from ghostcopyeditor.nlp.missing_predicate import (
    MissingPredicateHit,
    detect_missing_predicates,
    has_finite_predicate,
)
from ghostcopyeditor.nlp.spacy_runtime import (
    get_nlp,
    missing_predicate_skip_warning,
    nlp_unavailable_reason,
    warn_stderr_once,
)

__all__ = [
    "MissingPredicateHit",
    "detect_missing_predicates",
    "get_nlp",
    "has_finite_predicate",
    "missing_predicate_skip_warning",
    "nlp_unavailable_reason",
    "warn_stderr_once",
]
