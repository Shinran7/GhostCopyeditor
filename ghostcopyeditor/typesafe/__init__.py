"""TypeSafe.ai (Jev) judgment helpers for GhostCopyeditor.

Client lifecycle is owned by companion/analyze via ``async with``.
Never store the client in pipeline state.
"""

from __future__ import annotations

from ghostcopyeditor.typesafe.client import (
    TypesafeConfigError,
    ask,
    ensure_typesafe_api_key,
    ensure_typesafe_sdk,
)
from ghostcopyeditor.typesafe.judgments import run_typesafe_judgments
from ghostcopyeditor.typesafe.routing import resolve_typesafe_enabled

__all__ = [
    "TypesafeConfigError",
    "ask",
    "ensure_typesafe_api_key",
    "ensure_typesafe_sdk",
    "resolve_typesafe_enabled",
    "run_typesafe_judgments",
]
