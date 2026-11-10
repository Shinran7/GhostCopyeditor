"""Freeze guard: Autonomicon imports these names live from the sibling folder.

Autonomicon is under a code freeze and loads GhostCopyeditor on every run
(``autonomicon/agents/missing_predicate_detect.py``). Any rename, removed
field, or changed default here breaks it at once. Add beside; never change.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

import ghostcopyeditor.nlp as nlp_pkg
from ghostcopyeditor.nlp import MissingPredicateHit, detect_missing_predicates, get_nlp

RESONANCE = (
    "A rough chatter through Kieran's palm as he lifted the hauler "
    "clear of the buttress."
)


def test_nlp_exports_kept() -> None:
    frozen = {
        "MissingPredicateHit",
        "detect_missing_predicates",
        "get_nlp",
        "has_finite_predicate",
        "missing_predicate_skip_warning",
        "nlp_unavailable_reason",
        "sentence_has_finite_predicate",
        "warn_stderr_once",
    }
    assert frozen <= set(nlp_pkg.__all__)
    for name in frozen:
        assert hasattr(nlp_pkg, name)


def test_detect_signature_kept() -> None:
    params = inspect.signature(detect_missing_predicates).parameters
    assert list(params) == [
        "text",
        "min_tokens",
        "skip_dialogue_heavy",
        "require_period",
        "non_prose",
    ]
    assert params["min_tokens"].default == 5
    assert params["skip_dialogue_heavy"].default is True
    assert params["require_period"].default is True
    assert params["non_prose"].default is None


def test_hit_fields_kept() -> None:
    names = [f.name for f in dataclasses.fields(MissingPredicateHit)]
    assert names[:6] == ["start", "end", "excerpt", "root_text", "root_pos", "root_tag"]


def test_detect_output_kept() -> None:
    if get_nlp() is None:
        pytest.skip("spaCy model not installed")
    text = f"{RESONANCE} She lifted the hauler. The wind rose over the ridge."
    hits = detect_missing_predicates(text)
    assert len(hits) == 1
    hit = hits[0]
    assert hit.start == 0
    assert hit.excerpt == RESONANCE
    assert text[hit.start : hit.end].strip() == RESONANCE
