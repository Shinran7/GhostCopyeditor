"""Companion command — single chapter-NNN.md copy-edit."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel

from ghostcopyeditor.checkers.apply import apply_findings
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion.discovery import discover_companion
from ghostcopyeditor.llm import load_secrets
from ghostcopyeditor.models.report import CopyEditReport, ReportSummary
from ghostcopyeditor.pipeline.runner import run_chapter_pipeline
from ghostcopyeditor.typesafe import (
    TypesafeConfigError,
    ensure_typesafe_api_key,
    ensure_typesafe_sdk,
    resolve_typesafe_enabled,
)

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
    """Load one chapter, run pipeline, optionally apply deterministic fixes."""
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
    typesafe_on = resolve_typesafe_enabled(typesafe, cfg)
    llm_on = bool(cfg.llm_enabled and not no_llm) or bool(model and not no_llm)
    do_apply = apply or cfg.apply_default

    load_secrets()
    if typesafe_on:
        try:
            ensure_typesafe_sdk()
            ensure_typesafe_api_key()
        except TypesafeConfigError as exc:
            _print_error(str(exc), output_format=output_format)
            raise typer.Exit(code=1) from exc
        if verbose or output_format != "json":
            _ERR.print(
                f"[cyan]TypeSafe judgments: on[/cyan] "
                f"(floor {cfg.typesafe_confidence_floor})"
            )

    if verbose or output_format == "json":
        _ERR.print(
            f"[cyan]ghostcopyeditor companion:[/cyan] "
            f"chapter {discovery.chapter_number:03d} "
            f"({len(discovery.chapter.content)} chars)"
        )

    findings = asyncio.run(
        _run_with_optional_typesafe(
            discovery.chapter,
            cfg=cfg,
            typesafe_on=typesafe_on,
            llm_on=llm_on,
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
    report.summary = ReportSummary.from_findings(findings, chapters_scanned=1)
    _emit(report, output_format=output_format, output_path=output_path)


async def _run_with_optional_typesafe(
    chapter: Any,
    *,
    cfg: GhostCopyeditorConfig,
    typesafe_on: bool,
    llm_on: bool,
) -> list[Any]:
    if typesafe_on:
        from typesafe_sdk import AsyncTypeSafeClient

        async with AsyncTypeSafeClient() as client:
            return await run_chapter_pipeline(
                chapter,
                cfg=cfg,
                typesafe_client=client,
                typesafe_enabled=True,
                llm_enabled=llm_on,
            )
    return await run_chapter_pipeline(
        chapter,
        cfg=cfg,
        typesafe_enabled=False,
        llm_enabled=llm_on,
    )


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
