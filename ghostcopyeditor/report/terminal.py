"""Rich terminal summary for CopyEditReport."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ghostcopyeditor.models.finding import Finding, Severity
from ghostcopyeditor.models.report import CopyEditReport

_SEVERITY_ORDER = (
    Severity.ERROR,
    Severity.WARNING,
    Severity.SUGGESTION,
    Severity.INFO,
)

_SEVERITY_STYLE = {
    Severity.ERROR: "bold red",
    Severity.WARNING: "bold yellow",
    Severity.SUGGESTION: "bold cyan",
    Severity.INFO: "dim",
}

_DEFAULT_MAX_FINDINGS = 50


def render_report(
    report: CopyEditReport,
    *,
    console: Console | None = None,
    max_findings: int = _DEFAULT_MAX_FINDINGS,
) -> None:
    """Print a Rich summary grouped by severity then category."""
    con = console or Console()
    _render_header(con, report)
    _render_overview(con, report)
    if report.mode == "analyze" and len(report.chapters) > 1:
        _render_chapter_rollup(con, report)
    _render_findings(con, report, max_findings=max_findings)
    _render_may_look(con, report)
    if report.warnings:
        _render_warnings(con, report.warnings)
    con.print()


def _render_header(con: Console, report: CopyEditReport) -> None:
    title = report.manuscript_name or "Copy-edit report"
    mode = report.mode
    con.print()
    con.rule(f"[bold cyan]{title}[/bold cyan] ({mode})", style="cyan")


def _render_overview(con: Console, report: CopyEditReport) -> None:
    summary = report.summary
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("label", style="bold")
    table.add_column("value")

    table.add_row("Copyedits", str(summary.total_findings))
    table.add_row("You may look", str(len(report.may_look)))
    table.add_row(
        "By severity",
        _fmt_counts(summary.by_severity, order=[s.value for s in _SEVERITY_ORDER]),
    )
    table.add_row("By engine", _fmt_counts(summary.by_engine))
    table.add_row("Chapters scanned", str(summary.chapters_scanned))
    table.add_row("Applied", str(summary.applied_count))
    if report.apply:
        table.add_row("Apply mode", "on")

    con.print(Panel(table, title="Overview", border_style="dim"))


def _render_chapter_rollup(con: Console, report: CopyEditReport) -> None:
    table = Table(title="Per-chapter rollup", show_lines=False)
    table.add_column("Ch", justify="right", style="cyan")
    table.add_column("Title", ratio=1)
    table.add_column("Findings", justify="right")

    for chapter in report.chapters:
        table.add_row(
            str(chapter.chapter_number),
            chapter.title or "—",
            str(len(chapter.finding_ids)),
        )
    con.print(table)
    con.print()


def _render_findings(
    con: Console, report: CopyEditReport, *, max_findings: int
) -> None:
    findings = list(report.findings)
    if not findings:
        con.print("[dim]No findings.[/dim]")
        return

    ordered = _sort_findings(findings)
    shown = ordered[:max_findings]
    hidden = len(ordered) - len(shown)

    grouped: dict[str, dict[str, list[Finding]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for finding in shown:
        sev = str(finding.severity)
        cat = str(finding.category)
        grouped[sev][cat].append(finding)

    for severity in _SEVERITY_ORDER:
        sev_key = severity.value
        if sev_key not in grouped:
            continue
        style = _SEVERITY_STYLE.get(severity, "white")
        for category, items in sorted(grouped[sev_key].items()):
            renderables: list[Text] = []
            for finding in items:
                renderables.append(_finding_line(finding, style=style))
                renderables.append(Text())
            con.print(
                Panel(
                    Group(*renderables),
                    title=f"[bold]{sev_key} · {category}[/bold]",
                    border_style=style.replace("bold ", ""),
                    padding=(0, 2),
                )
            )

    if hidden > 0:
        con.print(f"[dim]… and {hidden} more finding(s).[/dim]")


def _render_may_look(con: Console, report: CopyEditReport) -> None:
    notes = list(report.may_look)
    if not notes:
        return
    lines: list[Text] = []
    for finding in notes[:_DEFAULT_MAX_FINDINGS]:
        word = str(finding.metadata.get("word") or "")
        sentence = finding.location.excerpt or ""
        line = Text()
        line.append(f"{word}: ", style="bold")
        line.append(sentence)
        lines.append(line)
    hidden = len(notes) - min(len(notes), _DEFAULT_MAX_FINDINGS)
    if hidden > 0:
        lines.append(Text(f"… and {hidden} more.", style="dim"))
    con.print(Panel(Group(*lines), title="You may look", border_style="dim"))


def _finding_line(finding: Finding, *, style: str) -> Text:
    loc = _format_location(finding)
    line = Text()
    line.append(f"{loc} ", style="bold")
    line.append(f"[{finding.severity}] ", style=style)
    line.append(finding.message)
    line.append(f"  ({finding.engine}", style="dim")
    if finding.rule_id:
        line.append(f" · {finding.rule_id}", style="dim")
    line.append(")", style="dim")
    if finding.applyable and finding.replacement:
        line.append(f"\n  write: {finding.replacement}", style="green")
    elif finding.suggestion:
        line.append(f"\n  note: {finding.suggestion}", style="dim")
    if finding.id:
        line.append(f"\n  id={finding.id}", style="dim")
    return line


def _format_location(finding: Finding) -> str:
    ch = finding.location.chapter_number
    line = finding.location.line_start
    if line is not None:
        return f"Ch {ch}:L{line}"
    return f"Ch {ch}"


def _render_warnings(con: Console, warnings: Iterable[str]) -> None:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("warn")
    for warning in warnings:
        table.add_row(Text(warning, style="yellow"))
    con.print(Panel(table, title="Warnings", border_style="yellow"))


def _sort_findings(findings: list[Finding]) -> list[Finding]:
    rank = {s.value: i for i, s in enumerate(_SEVERITY_ORDER)}

    def key(f: Finding) -> tuple:
        return (
            rank.get(str(f.severity), 99),
            str(f.category),
            f.location.chapter_number,
            f.location.line_start or 0,
            f.id,
        )

    return sorted(findings, key=key)


def _fmt_counts(counts: dict[str, int], order: list[str] | None = None) -> str:
    keys = order or sorted(counts)
    parts = [f"{k}={counts.get(k, 0)}" for k in keys if counts.get(k, 0)]
    if not parts:
        # Still show zeros for known keys when everything is empty.
        if order:
            return ", ".join(f"{k}=0" for k in order)
        return "none"
    return ", ".join(parts)


__all__ = ["render_report"]
