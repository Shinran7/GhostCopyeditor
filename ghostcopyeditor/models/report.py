"""Copy-edit report skeleton (findings top-level; chapters hold ids only)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from ghostcopyeditor import __version__
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import Category, Finding


@dataclass
class ChapterResult:
    """Per-chapter rollup. Stores finding ids only — not nested Finding objects."""

    chapter_number: int
    chapter_path: str
    title: str
    finding_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReportSummary:
    total_findings: int = 0
    by_severity: dict[str, int] = field(
        default_factory=lambda: {
            "error": 0,
            "warning": 0,
            "suggestion": 0,
            "info": 0,
        }
    )
    by_category: dict[str, int] = field(default_factory=dict)
    by_engine: dict[str, int] = field(
        default_factory=lambda: {
            "deterministic": 0,
            "typesafe": 0,
            "llm": 0,
        }
    )
    applied_count: int = 0
    chapters_scanned: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_findings(
        cls, findings: list[Finding], *, chapters_scanned: int
    ) -> ReportSummary:
        summary = cls(chapters_scanned=chapters_scanned, total_findings=len(findings))
        for finding in findings:
            sev = str(finding.severity)
            summary.by_severity[sev] = summary.by_severity.get(sev, 0) + 1
            cat = str(finding.category)
            summary.by_category[cat] = summary.by_category.get(cat, 0) + 1
            eng = str(finding.engine)
            summary.by_engine[eng] = summary.by_engine.get(eng, 0) + 1
            if finding.metadata.get("applied"):
                summary.applied_count += 1
        return summary


@dataclass
class CopyEditReport:
    """Autonomicon-shaped report. Full findings live only at the top level."""

    ghostcopyeditor_version: str
    mode: Literal["companion", "analyze"]
    generated_at: str
    manuscript_path: str
    manuscript_name: str
    story_slug: str
    chapter_number: int | None
    summary: ReportSummary
    findings: list[Finding] = field(default_factory=list)
    may_look: list[Finding] = field(default_factory=list)
    chapters: list[ChapterResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    typesafe_enabled: bool = False
    llm_enabled: bool = False
    apply: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON. Chapters expose ``finding_ids`` only."""
        return {
            "ghostcopyeditor_version": self.ghostcopyeditor_version,
            "mode": self.mode,
            "generated_at": self.generated_at,
            "manuscript_path": self.manuscript_path,
            "manuscript_name": self.manuscript_name,
            "story_slug": self.story_slug,
            "chapter_number": self.chapter_number,
            "summary": self.summary.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "may_look": [f.to_dict() for f in self.may_look],
            "chapters": [c.to_dict() for c in self.chapters],
            "warnings": list(self.warnings),
            "typesafe_enabled": self.typesafe_enabled,
            "llm_enabled": self.llm_enabled,
            "apply": self.apply,
        }

    @classmethod
    def empty(
        cls,
        *,
        mode: Literal["companion", "analyze"],
        manuscript_path: str,
        manuscript_name: str,
        story_slug: str,
        chapter_number: int | None,
        chapters: list[Chapter],
        typesafe_enabled: bool,
        llm_enabled: bool,
        apply: bool,
        warnings: list[str] | None = None,
        findings: list[Finding] | None = None,
        may_look: list[Finding] | None = None,
    ) -> CopyEditReport:
        """Build a report with optional findings (empty until engines land)."""
        findings = findings or []
        may_look = may_look or []
        chapter_results = [
            ChapterResult(
                chapter_number=ch.chapter_number,
                chapter_path=str(ch.source_path),
                title=ch.title,
                finding_ids=[f.id for f in findings if f.location.chapter_number == ch.chapter_number],
            )
            for ch in chapters
        ]
        return cls(
            ghostcopyeditor_version=__version__,
            mode=mode,
            generated_at=datetime.now(timezone.utc).isoformat(),
            manuscript_path=manuscript_path,
            manuscript_name=manuscript_name,
            story_slug=story_slug,
            chapter_number=chapter_number,
            summary=ReportSummary.from_findings(
                findings, chapters_scanned=len(chapters)
            ),
            findings=findings,
            may_look=may_look,
            chapters=chapter_results,
            warnings=list(warnings or []),
            typesafe_enabled=typesafe_enabled,
            llm_enabled=llm_enabled,
            apply=apply,
        )


def partition_action_list(
    findings: list[Finding],
) -> tuple[list[Finding], list[Finding]]:
    """Split copyedits from echo notes.

    Echo has no repair. It must not sit in the list a program revises.
    """
    action: list[Finding] = []
    may_look: list[Finding] = []
    for finding in findings:
        if finding.category == Category.ECHO or finding.rule_id == "echo.local_repeat":
            may_look.append(finding)
        else:
            action.append(finding)
    return action, may_look


__all__ = [
    "ChapterResult",
    "CopyEditReport",
    "ReportSummary",
    "partition_action_list",
]
