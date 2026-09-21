"""Analyze command — chapter folder combined report."""

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
from ghostcopyeditor.ingestion.discovery import discover_analyze
from ghostcopyeditor.llm import get_llm, load_secrets
from ghostcopyeditor.models.report import ReportSummary
from ghostcopyeditor.pipeline.runner import run_analyze_pipeline
from ghostcopyeditor.typesafe import (
    TypesafeConfigError,
    ensure_typesafe_api_key,
    ensure_typesafe_sdk,
    resolve_typesafe_enabled,
)

_ERR = Console(stderr=True)


def run_analyze(
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
    """Discover chapters, run pipeline, optionally apply deterministic fixes."""
    path = path.resolve()
    try:
        discovery = discover_analyze(path)
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
        nums = ", ".join(f"{ch.chapter_number:03d}" for ch in discovery.chapters)
        _ERR.print(
            f"[cyan]ghostcopyeditor analyze:[/cyan] "
            f"{len(discovery.chapters)} chapter(s) [{nums}]"
        )

    report = asyncio.run(
        _run_engines(
            discovery.chapters,
            cfg=cfg,
            typesafe_on=typesafe_on,
            llm_on=llm_on,
            llm=llm,
            manuscript_path=str(discovery.path),
            manuscript_name=discovery.manuscript_name,
            story_slug=discovery.story_slug,
            apply=do_apply,
            warnings=list(discovery.warnings),
        )
    )

    if do_apply:
        _, apply_warnings = apply_findings(discovery.chapters, report.findings)
        report.warnings.extend(apply_warnings)
        report.summary = ReportSummary.from_findings(
            report.findings, chapters_scanned=len(discovery.chapters)
        )

    _emit(report, output_format=output_format, output_path=output_path)


async def _run_engines(
    chapters: list[Any],
    *,
    cfg: GhostCopyeditorConfig,
    typesafe_on: bool,
    llm_on: bool,
    llm: Any | None,
    manuscript_path: str,
    manuscript_name: str,
    story_slug: str,
    apply: bool,
    warnings: list[str],
) -> Any:
    kwargs = {
        "cfg": cfg,
        "llm": llm,
        "typesafe_enabled": typesafe_on,
        "llm_enabled": llm_on,
        "mode": "analyze",
        "manuscript_path": manuscript_path,
        "manuscript_name": manuscript_name,
        "story_slug": story_slug,
        "chapter_number": None,
        "apply": apply,
        "warnings": warnings,
    }
    if typesafe_on:
        from typesafe_sdk import AsyncTypeSafeClient

        async with AsyncTypeSafeClient() as client:
            return await run_analyze_pipeline(
                chapters, typesafe_client=client, **kwargs
            )
    return await run_analyze_pipeline(chapters, **kwargs)


def _print_error(msg: str, *, output_format: str) -> None:
    if output_format == "json":
        _ERR.print(f"[red]Error:[/red] {msg}")
    else:
        rprint(f"[red]Error:[/red] {msg}")


def _emit(
    report,
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

    rprint(
        Panel(
            f"[green]analyze complete[/green]\n"
            f"Chapters scanned: {report.summary.chapters_scanned}\n"
            f"Path: {report.manuscript_path}\n"
            f"Findings: {report.summary.total_findings}\n"
            f"Applied: {report.summary.applied_count}",
            title="ghostcopyeditor",
        )
    )


__all__ = ["run_analyze"]
