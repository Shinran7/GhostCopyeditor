"""Load-once spaCy pipeline for missing-predicate detection."""

from __future__ import annotations

import logging
import sys
from typing import Any, TextIO

logger = logging.getLogger("ghostcopyeditor.nlp")

_NLP: Any | None = None
_LOAD_ERROR: str | None = None
_STDERR_ONCE = False

_SKIP_WARNING = (
    "missing_predicate skipped: install ghostcopyeditor[nlp] and run: "
    "python -m spacy download en_core_web_sm"
)


def get_nlp() -> Any | None:
    """Return shared spaCy pipeline or None if unavailable."""
    global _NLP, _LOAD_ERROR
    if _NLP is not None or _LOAD_ERROR is not None:
        return _NLP
    try:
        import spacy

        _NLP = spacy.load("en_core_web_sm", disable=["ner"])
    except Exception as exc:  # ImportError or OSError E050
        _LOAD_ERROR = str(exc)
        logger.warning("missing_predicate: spaCy unavailable (%s)", _LOAD_ERROR)
        return None
    return _NLP


def nlp_unavailable_reason() -> str | None:
    """None when ready; else human reason for report warnings[]."""
    get_nlp()
    return _LOAD_ERROR


def missing_predicate_skip_warning(cfg: Any) -> str | None:
    """Warning string when rule is enabled and NLP stack is missing."""
    if not getattr(cfg, "missing_predicate_enabled", True):
        return None
    if nlp_unavailable_reason() is None:
        return None
    return _SKIP_WARNING


def warn_stderr_once(stream: TextIO | None = None) -> None:
    """One-time companion stderr when NLP stack missing and rule enabled."""
    global _STDERR_ONCE
    if _STDERR_ONCE:
        return
    _STDERR_ONCE = True
    out = stream if stream is not None else sys.stderr
    print(_SKIP_WARNING, file=out)


def _reset_for_tests() -> None:
    """Clear singleton state between tests."""
    global _NLP, _LOAD_ERROR, _STDERR_ONCE
    _NLP = None
    _LOAD_ERROR = None
    _STDERR_ONCE = False


__all__ = [
    "get_nlp",
    "missing_predicate_skip_warning",
    "nlp_unavailable_reason",
    "warn_stderr_once",
]
