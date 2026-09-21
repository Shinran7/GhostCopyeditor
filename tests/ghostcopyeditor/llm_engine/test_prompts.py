"""Tests for garbled prompt templates."""

from __future__ import annotations

from ghostcopyeditor.llm_engine.prompts import (
    GARBLED_SYSTEM_PROMPT,
    build_garbled_user_prompt,
)


def test_system_prompt_asks_for_json_array() -> None:
    assert "JSON" in GARBLED_SYSTEM_PROMPT
    assert "excerpt" in GARBLED_SYSTEM_PROMPT
    assert "suggestion" in GARBLED_SYSTEM_PROMPT


def test_user_prompt_wraps_chapter() -> None:
    text = build_garbled_user_prompt("He walked.\n", chapter_number=18)
    assert "Chapter 018" in text
    assert "<chapter>" in text
    assert "He walked." in text
