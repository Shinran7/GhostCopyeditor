"""Rhythm notes: syntactic monotony in narration (report-only).

Calibrated on recent Autonomicon chapters against public-domain prose: the
strongest signal is runs of short sentences that each open with the subject
and go straight to the verb. Dialogue breaks a run and is never flagged.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Severity,
    location_from_span,
)

if TYPE_CHECKING:
    from ghostcopyeditor.nlp.sentence_shape import SentenceShape

_EXCERPT_CHARS = 160


def _runs(
    items: list[SentenceShape | None],
    key: Callable[[SentenceShape], object],
    min_len: int,
) -> list[list[SentenceShape]]:
    """Runs of consecutive shapes with the same non-None key. None breaks a run."""
    out: list[list[SentenceShape]] = []
    cur: list[SentenceShape] = []
    for item in [*items, None]:
        value = key(item) if item is not None else None
        if (
            item is not None
            and cur
            and value is not None
            and value == key(cur[-1])
            and item.scene == cur[-1].scene
        ):
            cur.append(item)
            continue
        if len(cur) >= min_len:
            out.append(cur)
        cur = [item] if item is not None and value is not None else []
    return out


def _excerpt(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= _EXCERPT_CHARS else flat[: _EXCERPT_CHARS - 1] + "…"


class RhythmChecker:
    """Same-opener runs, same-shape runs, and flat scenes."""

    rule_ids: ClassVar[tuple[str, ...]] = (
        "rhythm.same_opener_run",
        "rhythm.shape_run",
        "rhythm.flat_scene",
    )

    def check(self, chapter: Chapter, cfg: GhostCopyeditorConfig) -> list[Finding]:
        if not cfg.rhythm_enabled:
            return []
        # Imported here: nlp.sentences imports checkers.regions (import cycle).
        from ghostcopyeditor.nlp.sentence_shape import scene_metrics, sentence_shape
        from ghostcopyeditor.nlp.sentences import prose_sentences

        text = chapter.content
        sentences = prose_sentences(text)
        items: list[SentenceShape | None] = [
            None if s.dialogue else sentence_shape(s) for s in sentences
        ]
        findings: list[Finding] = []

        def note(
            run: list[SentenceShape], rule: str, message: str, meta: dict[str, object]
        ) -> None:
            start, end = run[0].start, run[-1].end
            findings.append(
                Finding(
                    id="",
                    category=Category.RHYTHM,
                    severity=Severity.SUGGESTION,
                    message=message,
                    location=location_from_span(
                        chapter, start, end, excerpt=_excerpt(text[start:end])
                    ),
                    engine=Engine.DETERMINISTIC,
                    suggestion="(vary sentence openings and structure)",
                    rule_id=rule,
                    applyable=False,
                    metadata={"sentences": len(run), **meta},
                )
            )

        for run in _runs(items, lambda s: s.opener or None, cfg.rhythm_opener_run):
            note(
                run,
                "rhythm.same_opener_run",
                f"{len(run)} sentences in a row start with “{run[0].opener}”.",
                {"opener": run[0].opener},
            )

        short = cfg.rhythm_short_words

        def plain(s: SentenceShape) -> object:
            return True if s.subject_first and s.words <= short else None

        for run in _runs(items, plain, cfg.rhythm_shape_run):
            note(
                run,
                "rhythm.shape_run",
                (
                    f"{len(run)} short sentences in a row, each opening "
                    "subject-then-verb."
                ),
                {"max_words": max(s.words for s in run)},
            )

        for scene in sorted({s.scene for s in sentences}):
            shapes = [i for i in items if i is not None and i.scene == scene]
            if len(shapes) < cfg.rhythm_min_scene_sentences:
                continue
            metrics = scene_metrics(shapes)
            variety = metrics["variety"]
            if variety is None or variety >= cfg.rhythm_flat_variety:
                continue
            start, end = shapes[0].start, shapes[-1].end
            findings.append(
                Finding(
                    id="",
                    category=Category.RHYTHM,
                    severity=Severity.WARNING,
                    message=(
                        f"Scene {scene} reads flat: variety {variety}/100 "
                        f"(limit {cfg.rhythm_flat_variety}). Average "
                        f"{metrics['narration_words_mean']} words; "
                        f"{_pct(metrics['subject_first_share'])} of sentences "
                        "open subject-then-verb."
                    ),
                    location=location_from_span(
                        chapter, start, end, excerpt=_excerpt(text[start:end])
                    ),
                    engine=Engine.DETERMINISTIC,
                    suggestion="(rework: mix lengths, openings, and clause structure)",
                    rule_id="rhythm.flat_scene",
                    applyable=False,
                    metadata={"scene": scene, **metrics},
                )
            )
        return findings


def _pct(value: object) -> str:
    return "n/a" if not isinstance(value, float) else f"{round(value * 100)}%"


__all__ = ["RhythmChecker"]
