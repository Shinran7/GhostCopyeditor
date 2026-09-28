"""Earth timeline anachronism checker (eff33fcf T2 / KD-18)."""

from __future__ import annotations

from pathlib import Path

from ghostcopyeditor.checkers.anachronism import AnachronismChecker
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import Category


def _chapter(text: str) -> Chapter:
    return Chapter(
        title="T",
        content=text,
        chapter_number=1,
        source_path=Path("/story/chapters/chapter-001.md"),
    )


def test_precambrian_and_telephone_pole_on_non_earth() -> None:
    text = (
        "On Eos Prime the pre-Cambrian ice sheet glittered.\n"
        "The relay mast stood like a telephone pole against the wind.\n"
    )
    findings = AnachronismChecker().check(_chapter(text), GhostCopyeditorConfig())
    assert findings
    assert all(f.category == Category.STYLE for f in findings)
    assert all(f.rule_id == "anachronism.earth_timeline" for f in findings)
    joined = " ".join(f.message.lower() for f in findings)
    assert "pre-cambrian" in joined or "pre-Cambrian".lower() in joined
    assert "telephone pole" in joined


def test_earth_setting_control_quiet() -> None:
    text = (
        "Back on Earth, the pre-Cambrian ice was a museum joke.\n"
        "A telephone pole leaned over the London street.\n"
    )
    findings = AnachronismChecker().check(_chapter(text), GhostCopyeditorConfig())
    assert findings == []
