"""Deterministic copy-edit checkers."""

from __future__ import annotations

from typing import ClassVar, Protocol

from ghostcopyeditor.checkers.apply import (
    apply_findings,
    apply_to_chapter,
    apply_to_content,
)
from ghostcopyeditor.checkers.echo import EchoChecker
from ghostcopyeditor.checkers.mechanics import MechanicsChecker
from ghostcopyeditor.checkers.style import StyleChecker
from ghostcopyeditor.checkers.wordiness import WordinessChecker
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import Finding


class Checker(Protocol):
    """Pluggable checker returning Finding records."""

    rule_ids: ClassVar[tuple[str, ...]]

    def check(self, chapter: Chapter, cfg: GhostCopyeditorConfig) -> list[Finding]: ...


# Stable registry order: mechanics → style → wordiness → echo.
CHECKER_REGISTRY: tuple[Checker, ...] = (
    MechanicsChecker(),
    StyleChecker(),
    WordinessChecker(),
    EchoChecker(),
)


def run_deterministic_checkers(
    chapter: Chapter, cfg: GhostCopyeditorConfig
) -> list[Finding]:
    """Run every registered deterministic checker in stable order."""
    findings: list[Finding] = []
    for checker in CHECKER_REGISTRY:
        findings.extend(checker.check(chapter, cfg))
    return findings


__all__ = [
    "CHECKER_REGISTRY",
    "Checker",
    "EchoChecker",
    "MechanicsChecker",
    "StyleChecker",
    "WordinessChecker",
    "apply_findings",
    "apply_to_chapter",
    "apply_to_content",
    "run_deterministic_checkers",
]
