"""Smoke for models package exports."""

from ghostcopyeditor.models import Category, CopyEditReport, Finding, Location


def test_models_exports() -> None:
    assert Category.GRAMMAR == "grammar"
    assert Finding is not None
    assert Location is not None
    assert CopyEditReport is not None
