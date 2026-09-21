"""Smoke test for typesafe package exports."""

from __future__ import annotations

from ghostcopyeditor import typesafe


def test_public_exports() -> None:
    assert hasattr(typesafe, "ensure_typesafe_sdk")
    assert hasattr(typesafe, "ensure_typesafe_api_key")
    assert hasattr(typesafe, "resolve_typesafe_enabled")
    assert hasattr(typesafe, "run_typesafe_judgments")
    assert hasattr(typesafe, "TypesafeConfigError")
