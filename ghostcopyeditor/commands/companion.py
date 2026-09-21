"""Companion command — single chapter-NNN.md copy-edit."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel

from ghostcopyeditor.checkers.apply import apply_findings
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion.discovery import discover_companion
from ghostcopyeditor.models.report import CopyEditReport, ReportSummary
from ghostcopyeditor.pipeline.runner import run_chapter_pipeline

_ERR = Console(stderr=True)


def run_companion(
    path: Path,
    *,
    output_format: str,
    output_path: Path | None,
    typesafe: bool | None,
    no_llm: bool,
    apply: bool,
    model: str | None,
    verbose: bool,
) -> None:
    """Load one chapter, run deterministic pipeline, optionally apply."""
    path = path.resolve()
    try:
        discovery = discover_companion(path)
    except FileNotFoundError as exc:
        _print_error(str(exc), output_format=output_format)
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        _print_error(str(exc), output_format=output_format)
        raise typer.Exit(code=1) from exc

    cfg = GhostCopyeditorConfig.load(path)
    typesafe_on = cfg.typesafe_enabled if typesafe is None else typesafe
    llm_on = bool(cfg.llm_enabled and not no_llm) or bool(model and not no_llm)
    do_apply = apply or cfg.apply_default

    if verbose or output_format == "json":
        _ERR.print(
            f"[cyan]ghostcopyeditor companion:[/cyan] "
            f"chapter {discovery.chapter_number:03d} "
            f"({len(discovery.chapter.content)} chars)"
        )

    findings = asyncio.run(
        run_chapter_pipeline(
            discovery.chapter,
            cfg=cfg,
            typesafe_enabled=typesafe_on,
            llm_enabled=llm_on,
        )
    )

    warnings = list(discovery.warnings)
    if do_apply:
        _, apply_warnings = apply_findings([discovery.chapter], findings)
        warnings.extend(apply_warnings)

    report = CopyEditReport.empty(
        mode="companion",
        manuscript_path=str(discovery.path),
        manuscript_name=discovery.manuscript_name,
        story_slug=discovery.story_slug,
        chapter_number=discovery.chapter_number,
        chapters=[discovery.chapter],
        typesafe_enabled=typesafe_on,
        llm_enabled=llm_on,
        apply=do_apply,
        warnings=warnings,
        findings=findings,
    )
    # Recompute summary so applied_count reflects metadata.applied.
    report.summary = ReportSummary.from_findings(
        findings, chapters_scanned=1
    )
    _emit(report, output_format=output_format, output_path=output_path)


def _print_error(msg: str, *, output_format: str) -> None:
    if output_format == "json":
        _ERR.print(f"[red]Error:[/red] {msg}")
    else:
        rprint(f"[red]Error:[/red] {msg}")


def _emit(
    report: CopyEditReport,
    *,
    output_format: str,
    output_path: Path | None,
) -> None:
    payload = report.to_dict()
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if output_format == "json":
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return

    applied = report.summary.applied_count
    rprint(
        Panel(
            f"[green]companion complete[/green]\n"
            f"Chapter: {report.chapter_number}\n"
            f"Path: {report.manuscript_path}\n"
            f"Findings: {report.summary.total_findings}\n"
            f"Applied: {applied}",
            title="ghostcopyeditor",
        )
    )


__all__ = ["run_companion"]
