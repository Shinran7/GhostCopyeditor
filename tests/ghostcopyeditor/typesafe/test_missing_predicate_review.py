"""Per-hit TypeSafe confirm for missing-predicate findings."""

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
from ghostcopyeditor.typesafe.missing_predicate_review import (
    review_missing_predicate_findings,
)
from ghostcopyeditor.typesafe.per_hit_budget import PerHitAskBudget
from ghostcopyeditor.typesafe.state import (
    CANDIDATE_MAX_COUNT,
    sample_candidate_passages,
)


def _chapter(text: str) -> Chapter:
    return Chapter("T", text, 1, Path("chapter-001.md"))


def _mp(excerpt: str, *, start: int = 0, root: str = "chatter") -> Finding:
    return Finding(
        id="",
        category=Category.GRAMMAR,
        severity=Severity.WARNING,
        message="Main clause may be missing a finite verb (predicate).",
        location=Location(
            chapter_number=1,
            chapter_path="chapter-001.md",
            char_start=start,
            char_end=start + len(excerpt),
            excerpt=excerpt,
        ),
        engine=Engine.DETERMINISTIC,
        rule_id="mech.missing_predicate",
        applyable=False,
        metadata={"root_text": root, "root_pos": "NOUN", "root_tag": "NN"},
    )


class _Client:
    def __init__(self, label: str, confidence: float = 0.9) -> None:
        self.label = label
        self.confidence = confidence
        self.calls = 0
        self.states: list[dict] = []

    async def system_one(self, **kwargs: object) -> SimpleNamespace:
        self.calls += 1
        state = kwargs["state"]
        assert isinstance(state, dict)
        self.states.append(state)
        return SimpleNamespace(
            choices={
                "copy.missing_predicate": SimpleNamespace(
                    choice=self.label,
                    confidence=self.confidence,
                )
            },
            nouls={},
        )


class _SequenceClient:
    """Return a fixed sequence of labels."""

    def __init__(self, labels: list[tuple[str, float]]) -> None:
        self.labels = list(labels)
        self.calls = 0

    async def system_one(self, **kwargs: object) -> SimpleNamespace:
        del kwargs
        label, conf = self.labels[min(self.calls, len(self.labels) - 1)]
        self.calls += 1
        return SimpleNamespace(
            choices={
                "copy.missing_predicate": SimpleNamespace(
                    choice=label, confidence=conf
                )
            },
            nouls={},
        )


def test_intentional_demotes_to_info() -> None:
    text = "A rough chatter through Kieran's palm as he lifted the hauler."
    finding = _mp(text)
    kept = asyncio.run(
        review_missing_predicate_findings(
            _chapter(text),
            [finding],
            _Client("intentional"),
            GhostCopyeditorConfig(),
        )
    )
    assert len(kept) == 1
    assert kept[0].severity == Severity.INFO
    assert kept[0].metadata["missing_predicate_review"] == "intentional"


def test_broken_keeps_warning() -> None:
    text = "A rough chatter through Kieran's palm as he lifted the hauler."
    finding = _mp(text)
    kept = asyncio.run(
        review_missing_predicate_findings(
            _chapter(text),
            [finding],
            _Client("broken"),
            GhostCopyeditorConfig(),
        )
    )
    assert kept[0].severity == Severity.WARNING


def test_mixed_hits_independent() -> None:
    a = _mp("Running through the dark corridor.", start=0, root="Running")
    b_text = "Finished with the long haul."
    b = _mp(b_text, start=100, root="Finished")
    client = _SequenceClient([("intentional", 0.9), ("broken", 0.9)])
    kept = asyncio.run(
        review_missing_predicate_findings(
            _chapter("x" * 200),
            [a, b],
            client,
            GhostCopyeditorConfig(),
        )
    )
    assert kept[0].severity == Severity.INFO
    assert kept[1].severity == Severity.WARNING


def test_typesafe_off_keeps_warning() -> None:
    text = "A rough chatter through Kieran's palm as he lifted the hauler."
    finding = _mp(text)
    kept = asyncio.run(
        review_missing_predicate_findings(
            _chapter(text),
            [finding],
            None,
            GhostCopyeditorConfig(),
        )
    )
    assert kept[0].severity == Severity.WARNING


def test_confirm_flag_off_skips_ask() -> None:
    text = "A rough chatter through Kieran's palm as he lifted the hauler."
    finding = _mp(text)
    client = _Client("intentional")
    kept = asyncio.run(
        review_missing_predicate_findings(
            _chapter(text),
            [finding],
            client,
            GhostCopyeditorConfig(missing_predicate_typesafe_confirm=False),
        )
    )
    assert client.calls == 0
    assert kept[0].severity == Severity.WARNING


def test_budget_exhaustion_keeps_warning_unreviewed() -> None:
    findings = [_mp(f"Running through the dark corridor {i}.", start=i * 40) for i in range(3)]
    client = _Client("intentional")
    budget = PerHitAskBudget(remaining=1)
    kept = asyncio.run(
        review_missing_predicate_findings(
            _chapter("x" * 200),
            findings,
            client,
            GhostCopyeditorConfig(),
            budget=budget,
        )
    )
    assert client.calls == 1
    assert budget.used == 1
    assert kept[0].severity == Severity.INFO
    assert kept[1].metadata.get("missing_predicate_review") == "budget_exhausted"
    assert kept[1].severity == Severity.WARNING


def test_missing_predicate_survives_fragment_saturation() -> None:
    # Eight fragment paragraphs plus one missing-predicate span.
    fragments = [
        (
            f"Fragment paragraph number {i} never ends with terminal punctuation "
            "and stays longer than forty characters on purpose"
        )
        for i in range(8)
    ]
    mp_excerpt = (
        "A rough chatter through Kieran's palm as he lifted the hauler "
        "clear of the buttress."
    )
    content = "\n\n".join(fragments + [mp_excerpt])
    start = content.index(mp_excerpt)
    chapter = _chapter(content)
    finding = _mp(mp_excerpt, start=start)
    cands = sample_candidate_passages(chapter, [finding])
    assert len(cands) == CANDIDATE_MAX_COUNT
    assert any(c["source"] == "missing_predicate" for c in cands)
    assert any(mp_excerpt[:40] in c["text"] for c in cands)
