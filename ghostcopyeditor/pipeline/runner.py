"""Chapter pipeline: deterministic → (TypeSafe) → (LLM) → IDs → dedupe."""

from __future__ import annotations

from typing import Any

from ghostcopyeditor.checkers import run_deterministic_checkers
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import (
    Engine,
    Finding,
    assign_finding_ids,
)
from ghostcopyeditor.models.report import ChapterResult, CopyEditReport


def _normalize_message(message: str) -> str:
    return " ".join(message.lower().split())


def _spans_overlap(a: Finding, b: Finding) -> bool:
    a_start, a_end = a.location.char_start, a.location.char_end
    b_start, b_end = b.location.char_start, b.location.char_end
    if None in (a_start, a_end, b_start, b_end):
        return False
    assert a_start is not None
    assert a_end is not None
    assert b_start is not None
    assert b_end is not None
    inter = max(0, min(a_end, b_end) - max(a_start, b_start))
    union = max(a_end, b_end) - min(a_start, b_start)
    if union <= 0:
        return False
    contained = (a_start >= b_start and a_end <= b_end) or (
        b_start >= a_start and b_end <= a_end
    )
    return inter / union >= 0.5 or contained


def _same_bucket(a: Finding, b: Finding) -> bool:
    if a.location.chapter_number != b.location.chapter_number:
        return False
    if a.category != b.category:
        return False
    a_has = a.location.char_start is not None and a.location.char_end is not None
    b_has = b.location.char_start is not None and b.location.char_end is not None
    if a_has and b_has:
        return _spans_overlap(a, b)
    if not a_has and not b_has:
        return _normalize_message(a.message) == _normalize_message(b.message)
    return False


_ENGINE_RANK = {
    Engine.DETERMINISTIC: 3,
    Engine.TYPESAFE: 2,
    Engine.LLM: 1,
}


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    """Drop same-bucket duplicates. Prefer deterministic > typesafe > llm."""
    kept: list[Finding] = []
    for finding in findings:
        drop = False
        for i, prior in enumerate(kept):
            if not _same_bucket(prior, finding):
                continue
            prior_rank = _ENGINE_RANK.get(prior.engine, 0)
            new_rank = _ENGINE_RANK.get(finding.engine, 0)
            if new_rank > prior_rank:
                kept[i] = finding
            # else keep prior (first in list when same engine)
            drop = True
            break
        if not drop:
            kept.append(finding)
    return kept


async def run_chapter_pipeline(
    chapter: Chapter,
    *,
    cfg: GhostCopyeditorConfig,
    llm: Any | None = None,
    typesafe_client: Any | None = None,
    typesafe_enabled: bool = False,
    llm_enabled: bool = False,
) -> list[Finding]:
    """Run engines for one chapter, assign IDs, then dedupe once."""
    findings: list[Finding] = []
    findings.extend(run_deterministic_checkers(chapter, cfg))
    if typesafe_enabled and typesafe_client is not None:
        from ghostcopyeditor.typesafe import run_typesafe_judgments

        findings.extend(
            await run_typesafe_judgments(
                chapter, findings, typesafe_client, cfg
            )
        )
    if llm_enabled and llm is not None:
        del llm  # pragma: no cover - PR5
    findings = assign_finding_ids(findings, chapter.chapter_number)
    return dedupe_findings(findings)


async def run_analyze_pipeline(
    chapters: list[Chapter],
    *,
    cfg: GhostCopyeditorConfig,
    llm: Any | None = None,
    typesafe_client: Any | None = None,
    typesafe_enabled: bool = False,
    llm_enabled: bool = False,
    mode: str = "analyze",
    manuscript_path: str = "",
    manuscript_name: str = "",
    story_slug: str = "",
    chapter_number: int | None = None,
    apply: bool = False,
    warnings: list[str] | None = None,
) -> CopyEditReport:
    """Run the chapter pipeline on each chapter and build a combined report."""
    all_findings: list[Finding] = []
    chapter_results: list[ChapterResult] = []
    for chapter in chapters:
        fs = await run_chapter_pipeline(
            chapter,
            cfg=cfg,
            llm=llm,
            typesafe_client=typesafe_client,
            typesafe_enabled=typesafe_enabled,
            llm_enabled=llm_enabled,
        )
        all_findings.extend(fs)
        chapter_results.append(
            ChapterResult(
                chapter_number=chapter.chapter_number,
                chapter_path=str(chapter.source_path),
                title=chapter.title,
                finding_ids=[f.id for f in fs],
            )
        )

    from datetime import UTC, datetime

    from ghostcopyeditor import __version__
    from ghostcopyeditor.models.report import ReportSummary

    return CopyEditReport(
        ghostcopyeditor_version=__version__,
        mode=mode,  # type: ignore[arg-type]
        generated_at=datetime.now(UTC).isoformat(),
        manuscript_path=manuscript_path,
        manuscript_name=manuscript_name,
        story_slug=story_slug,
        chapter_number=chapter_number,
        summary=ReportSummary.from_findings(
            all_findings, chapters_scanned=len(chapters)
        ),
        findings=all_findings,
        chapters=chapter_results,
        warnings=list(warnings or []),
        typesafe_enabled=typesafe_enabled,
        llm_enabled=llm_enabled,
        apply=apply,
    )


__all__ = [
    "dedupe_findings",
    "run_analyze_pipeline",
    "run_chapter_pipeline",
]
