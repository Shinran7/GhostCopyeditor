"""Questions module correspondence test; full cases in test_suite.py."""

from __future__ import annotations

from ghostcopyeditor.typesafe import questions


def test_questions_exports() -> None:
    assert "copy.grammar_ambiguity" in questions.COPY_EDIT_QUESTIONS
    assert callable(questions.copy_edit_questions)
