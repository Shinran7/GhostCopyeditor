"""LLM helpers — secrets loading (provider factory lands in a later PR)."""

from __future__ import annotations

import os


def load_secrets() -> None:
    """Load API keys from secrets/llm.env if it exists.

    Environment variables already set take precedence over file values.
    """
    from ghostcopyeditor.paths import find_secrets_env

    secrets_path = find_secrets_env()
    if secrets_path is None:
        return

    for line in secrets_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if value and key not in os.environ:
            os.environ[key] = value


def get_llm(*_args: object, **_kwargs: object) -> None:
    """Stub until the LLM provider factory lands (PR 5)."""
    raise NotImplementedError("get_llm is not implemented yet")
