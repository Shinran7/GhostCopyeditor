"""Tests for package version export."""

from __future__ import annotations

from ghostcopyeditor import __version__


def test_version() -> None:
    assert __version__ == "0.1.0"
