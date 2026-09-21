"""TypeSafe keeps real garble and drops point-of-view self-correction."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Location,
    Severity,
)
from ghostcopyeditor.pipeline.runner import run_chapter_pipeline
from ghostcopyeditor.typesafe.garbled_review import review_garbled_findings


def _chapter(text: str) -> Chapter:
    return Chapter("T", text, 1, Path("chapter-001.md"))


def _garble(excerpt: str, suggestion: str, *, applyable: bool = True) -> Finding:
    return Finding(
        id="",
        category=Category.GARBLED,
        severity=Severity.ERROR,
        message="Flagged.",
        location=Location(
            chapter_number=1,
            chapter_path="chapter-001.md",
            char_start=0,
            char_end=len(excerpt),
            excerpt=excerpt,
        ),
        engine=Engine.LLM,
        suggestion=suggestion,
        rule_id="llm.garbled",
        applyable=applyable,
        replacement=suggestion if applyable else None,
        metadata={"expected_old": excerpt} if applyable else {},
    )


class _Client:
    def __init__(self, label: str, confidence: float = 0.9) -> None:
        self.label = label
        self.confidence = confidence
        self.states: list[dict] = []

    async def system_one(self, **kwargs: object) -> SimpleNamespace:
        state = kwargs["state"]
        assert isinstance(state, dict)
        self.states.append(state)
        return SimpleNamespace(
            choices={
                "copy.garbled_or_voice": SimpleNamespace(
                    choice=self.label,
                    confidence=self.confidence,
                )
            },
            nouls={},
        )


def test_voice_is_dropped_and_context_is_sent() -> None:
    text = "which measured the morning... No. Which measured the air. He knelt."
    finding = _garble(
        "which measured the morning... No. Which measured the air.",
        "which measured the air.",
    )
    client = _Client("voice")
    kept = asyncio.run(
        review_garbled_findings(
            _chapter(text),
            [finding],
            client,
            GhostCopyeditorConfig(),
        )
    )
    assert kept == []
    assert "No." in client.states[0]["surrounding_prose"]
    assert client.states[0]["flagged_excerpt"].startswith("which measured")


def test_confirmed_garble_stays_applyable() -> None:
    text = "It stanchions were iron to the root."
    finding = _garble(text, "Its stanchions were iron to the root.")
    kept = asyncio.run(
        review_garbled_findings(
            _chapter(text),
            [finding],
            _Client("garbled", 0.8),
            GhostCopyeditorConfig(),
        )
    )
    assert len(kept) == 1
    assert kept[0].applyable is True
    assert kept[0].replacement.startswith("Its ")


def test_low_confidence_is_kept_but_not_applyable() -> None:
    text = "It stanchions were iron to the root."
    finding = _garble(text, "Its stanchions were iron to the root.")
    kept = asyncio.run(
        review_garbled_findings(
            _chapter(text),
            [finding],
            _Client("garbled", 0.2),
            GhostCopyeditorConfig(),
        )
    )
    assert len(kept) == 1
    assert kept[0].applyable is False
    assert kept[0].replacement is None


def test_pipeline_drops_brute_echo() -> None:
    from ghostcopyeditor.checkers.echo import EchoChecker

    text = "The shadow moved. Another shadow waited. A third shadow rose.\n"
    chapter = _chapter(text)
    raw = EchoChecker().check(chapter, GhostCopyeditorConfig())
    assert any(f.rule_id == "echo.local_repeat" for f in raw)
    findings = asyncio.run(run_chapter_pipeline(chapter, cfg=GhostCopyeditorConfig()))
    assert all(f.rule_id != "echo.local_repeat" for f in findings)
