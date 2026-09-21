"""Client module correspondence test; full cases in test_suite.py."""

from __future__ import annotations

from ghostcopyeditor.typesafe import client


def test_client_exports() -> None:
    assert hasattr(client, "TypesafeConfigError")
    assert hasattr(client, "ensure_typesafe_sdk")
    assert hasattr(client, "ensure_typesafe_api_key")
    assert hasattr(client, "ask")
