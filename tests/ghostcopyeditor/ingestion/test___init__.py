"""Smoke for ingestion package exports."""

from ghostcopyeditor.ingestion import Chapter


def test_chapter_export() -> None:
    assert Chapter.__dataclass_fields__  # type: ignore[attr-defined]
