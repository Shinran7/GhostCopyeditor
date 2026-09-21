"""Analyze command — chapter folder combined report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel

from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion.discovery import discover_analyze
from ghostcopyeditor.models.report import CopyEditReport

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
    """Discover chapters in order and emit an empty-findings stub report."""
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
    typesafe_on = cfg.typesafe_enabled if typesafe is None else typesafe
    llm_on = bool(cfg.llm_enabled and not no_llm) or bool(model and not no_llm)

    if verbose or output_format == "json":
        nums = ", ".join(f"{ch.chapter_number:03d}" for ch in discovery.chapters)
        _ERR.print(
            f"[cyan]ghostcopyeditor analyze:[/cyan] "
            f"{len(discovery.chapters)} chapter(s) [{nums}]"
        )

    report = CopyEditReport.empty(
        mode="analyze",
        manuscript_path=str(discovery.path),
        manuscript_name=discovery.manuscript_name,
        story_slug=discovery.story_slug,
        chapter_number=None,
        chapters=discovery.chapters,
        typesafe_enabled=typesafe_on,
        llm_enabled=llm_on,
        apply=apply,
        warnings=discovery.warnings,
        findings=[],
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

    rprint(
        Panel(
            f"[green]analyze complete[/green] — engines not wired yet.\n"
            f"Chapters scanned: {report.summary.chapters_scanned}\n"
            f"Path: {report.manuscript_path}\n"
            f"Findings: {report.summary.total_findings}",
            title="ghostcopyeditor",
        )
    )


__all__ = ["run_analyze"]
