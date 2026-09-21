"""Analyze command — chapter folder combined report."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import typer
from rich import print as rprint
from rich.console import Console

from ghostcopyeditor.checkers.apply import apply_findings
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.canon import canon_file_findings, load_cast
from ghostcopyeditor.ingestion.discovery import discover_analyze
from ghostcopyeditor.lexicon import lexicon_notice, load_lexicon
from ghostcopyeditor.llm import get_llm, load_secrets
from ghostcopyeditor.models.finding import assign_finding_ids
from ghostcopyeditor.models.report import ReportSummary
from ghostcopyeditor.pipeline.runner import run_analyze_pipeline
from ghostcopyeditor.report import export_json, persist_report_json, render_report
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
    lexicon = load_lexicon(discovery.story_dir)
    cast = load_cast(discovery.story_dir)
    warnings = list(discovery.warnings)
    notice = lexicon_notice(lexicon, discovery.story_dir)
    if notice:
        warnings.append(notice)
    if cast:
        warnings.append(f"Book cast: {len(cast)} characters.")
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
            warnings=warnings,
            lexicon=lexicon,
            cast=cast,
        )
    )

    file_notes = assign_finding_ids(canon_file_findings(discovery.story_dir), 0)
    if file_notes:
        report.findings = file_notes + list(report.findings)
        report.summary = ReportSummary.from_findings(
            report.findings, chapters_scanned=len(discovery.chapters)
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
    lexicon: Any | None = None,
    cast: tuple[Any, ...] = (),
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
        "lexicon": lexicon,
        "cast": cast,
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


__all__ = ["run_analyze"]
