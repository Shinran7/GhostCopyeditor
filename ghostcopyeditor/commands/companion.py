"""Companion command — single chapter-NNN.md copy-edit."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import typer
from rich import print as rprint
from rich.console import Console

from ghostcopyeditor.checkers.apply import apply_findings
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion.discovery import discover_companion
from ghostcopyeditor.llm import get_llm, load_secrets
from ghostcopyeditor.models.report import CopyEditReport, ReportSummary
from ghostcopyeditor.pipeline.runner import run_chapter_pipeline
from ghostcopyeditor.report import export_json, persist_report_json, render_report
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

    llm = None
    if llm_on:
        llm = get_llm(model, manuscript_path=path)
        llm_type = getattr(llm, "_llm_type", None)
        requested = (model or cfg.model or "").strip().lower()
        if llm_type == "stub" and requested != "stub":
            _print_error(
                "LLM engine is enabled but no usable chat-model API key was found.\n"
                "  Set the provider key in secrets/llm.env, pass --model stub "
                "(tests only), or pass --no-llm.",
                output_format=output_format,
            )
            raise typer.Exit(code=1)
        if verbose or output_format != "json":
            _ERR.print(f"[cyan]LLM garbled engine: on[/cyan] (model={requested or 'config'})")

    if verbose or output_format == "json":
        _ERR.print(
            f"[cyan]ghostcopyeditor companion:[/cyan] "
            f"chapter {discovery.chapter_number:03d} "
            f"({len(discovery.chapter.content)} chars)"
        )

    findings = asyncio.run(
        _run_engines(
            discovery.chapter,
            cfg=cfg,
            typesafe_on=typesafe_on,
            llm_on=llm_on,
            llm=llm,
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


async def _run_engines(
    chapter: Any,
    *,
    cfg: GhostCopyeditorConfig,
    typesafe_on: bool,
    llm_on: bool,
    llm: Any | None,
) -> list[Any]:
    if typesafe_on:
        from typesafe_sdk import AsyncTypeSafeClient

        async with AsyncTypeSafeClient() as client:
            return await run_chapter_pipeline(
                chapter,
                cfg=cfg,
                llm=llm,
                typesafe_client=client,
                typesafe_enabled=True,
                llm_enabled=llm_on,
            )
    return await run_chapter_pipeline(
        chapter,
        cfg=cfg,
        llm=llm,
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
    persist_path = persist_report_json(
        report,
        manuscript_path=Path(report.manuscript_path),
        also_path=output_path,
    )
    _ERR.print(f"[dim]Wrote {persist_path}[/dim]")

    if output_format == "json":
        export_json(report)
        return

    render_report(report)


__all__ = ["run_companion"]
