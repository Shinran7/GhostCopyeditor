"""Smoke test for llm_engine package exports."""

from __future__ import annotations

from ghostcopyeditor import llm_engine


def test_public_exports() -> None:
    assert hasattr(llm_engine, "run_llm_garbled")
