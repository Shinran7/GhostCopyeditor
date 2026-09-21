"""JSON export and on-disk persistence for CopyEditReport.

Stdout JSON matches the Autonomicon-stable schema. Inside an Autonomicon
story the file is ``stories/<slug>/reports/ghostcopyeditor-...``. Elsewhere
it is ``.ghostcopyeditor/<story-slug>/reports/``.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from ghostcopyeditor.models.report import CopyEditReport
from ghostcopyeditor.paths import (
    autonomicon_reports_dir,
    reports_dir,
    story_state_dir_for,
)

REQUIRED_TOP_LEVEL_KEYS = frozenset(
    {
        "ghostcopyeditor_version",
        "mode",
        "generated_at",
        "manuscript_path",
        "manuscript_name",
        "story_slug",
        "chapter_number",
        "summary",
        "findings",
        "may_look",
        "chapters",
        "warnings",
        "typesafe_enabled",
        "llm_enabled",
        "apply",
    }
)

REQUIRED_SUMMARY_KEYS = frozenset(
    {
        "total_findings",
        "by_severity",
        "by_category",
        "by_engine",
        "applied_count",
        "chapters_scanned",
    }
)

REQUIRED_CHAPTER_KEYS = frozenset(
    {
        "chapter_number",
        "chapter_path",
        "title",
        "finding_ids",
    }
)


def report_to_payload(report: CopyEditReport) -> dict[str, Any]:
    """Serialize a report to the Autonomicon JSON object."""
    return report.to_dict()


def export_json(
    report: CopyEditReport,
    *,
    output: TextIO | None = None,
    output_path: Path | None = None,
    indent: int = 2,
) -> str:
    """Serialize *report* as JSON.

    Writes to ``output_path`` and/or ``output`` (default: stdout). Always
    returns the JSON string (with trailing newline omitted from the return
    value; writers append a newline).
    """
    payload = report_to_payload(report)
    text = json.dumps(payload, indent=indent, ensure_ascii=False)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")

    if output is not None:
        output.write(text + "\n")
    elif output_path is None:
        sys.stdout.write(text + "\n")

    return text


def report_persist_path(
    report: CopyEditReport,
    *,
    project_root: Path | None = None,
    manuscript_path: Path | None = None,
    generated_at: datetime | None = None,
) -> Path:
    """Return the canonical on-disk path for *report* (does not write).

    Companion: ``companion-chNNN.json`` (latest wins).
    Analyze: ``analyze-YYYYMMDD-HHMMSS.json`` (collision suffix if needed).
    Under ``stories/<slug>/`` the names are prefixed ``ghostcopyeditor-`` and
    the folder is that story's ``reports/`` directory.
    """
    ms_path = Path(manuscript_path or report.manuscript_path)
    story_reports = autonomicon_reports_dir(ms_path)
    if story_reports is not None:
        out_dir = story_reports
        prefix = "ghostcopyeditor-"
    else:
        state = story_state_dir_for(ms_path, project_root=project_root)
        out_dir = reports_dir(state)
        prefix = ""
    out_dir.mkdir(parents=True, exist_ok=True)

    if report.mode == "companion":
        chapter = report.chapter_number if report.chapter_number is not None else 0
        return out_dir / f"{prefix}companion-ch{chapter:03d}.json"

    stamp = generated_at or datetime.now(timezone.utc)
    base = f"{prefix}analyze-{stamp.strftime('%Y%m%d-%H%M%S')}"
    candidate = out_dir / f"{base}.json"
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = out_dir / f"{base}-{n}.json"
        if not candidate.exists():
            return candidate
        n += 1


def persist_report_json(
    report: CopyEditReport,
    *,
    project_root: Path | None = None,
    manuscript_path: Path | None = None,
    also_path: Path | None = None,
    generated_at: datetime | None = None,
) -> Path:
    """Write JSON under ``.ghostcopyeditor/<story-slug>/reports/``.

    Optionally also write ``also_path`` (CLI ``-o``). Returns the canonical
    persist path.
    """
    path = report_persist_path(
        report,
        project_root=project_root,
        manuscript_path=manuscript_path,
        generated_at=generated_at,
    )
    text = json.dumps(report_to_payload(report), indent=2, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    if also_path is not None:
        also = also_path.resolve()
        also.parent.mkdir(parents=True, exist_ok=True)
        also.write_text(text, encoding="utf-8")

    return path


def validate_autonomicon_schema(payload: dict[str, Any]) -> list[str]:
    """Return human-readable schema problems (empty list means OK)."""
    errors: list[str] = []
    missing = REQUIRED_TOP_LEVEL_KEYS - set(payload)
    if missing:
        errors.append(f"missing top-level keys: {sorted(missing)}")

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
    else:
        missing_summary = REQUIRED_SUMMARY_KEYS - set(summary)
        if missing_summary:
            errors.append(f"missing summary keys: {sorted(missing_summary)}")

    findings = payload.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be a list")
        findings = []

    ids = [f.get("id") for f in findings if isinstance(f, dict)]
    if len(ids) != len(set(ids)):
        errors.append("findings[].id values must be unique")
    for finding in findings:
        if isinstance(finding, dict) and finding.get("rule_id") == "echo.local_repeat":
            errors.append("echo notes must not sit in findings; use may_look")
            break

    may_look = payload.get("may_look")
    if not isinstance(may_look, list):
        errors.append("may_look must be a list")

    by_id = {f["id"]: f for f in findings if isinstance(f, dict) and "id" in f}

    for finding in findings:
        if not isinstance(finding, dict):
            errors.append("finding entry must be an object")
            continue
        if finding.get("applyable") is True:
            meta = finding.get("metadata") or {}
            excerpt = ""
            loc = finding.get("location") or {}
            if isinstance(loc, dict):
                excerpt = loc.get("excerpt") or ""
            expected = meta.get("expected_old") if isinstance(meta, dict) else None
            if expected is None and not excerpt:
                errors.append(
                    f"applyable finding {finding.get('id')!r} needs "
                    "metadata.expected_old (or a non-empty excerpt)"
                )

    chapters = payload.get("chapters")
    if not isinstance(chapters, list):
        errors.append("chapters must be a list")
        return errors

    for i, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            errors.append(f"chapters[{i}] must be an object")
            continue
        if "findings" in chapter:
            errors.append(f"chapters[{i}] must not include nested findings")
        missing_ch = REQUIRED_CHAPTER_KEYS - set(chapter)
        if missing_ch:
            errors.append(f"chapters[{i}] missing keys: {sorted(missing_ch)}")
        for fid in chapter.get("finding_ids") or []:
            if fid not in by_id:
                errors.append(
                    f"chapters[{i}] finding_id {fid!r} does not resolve "
                    "to a top-level finding"
                )

    return errors


__all__ = [
    "REQUIRED_CHAPTER_KEYS",
    "REQUIRED_SUMMARY_KEYS",
    "REQUIRED_TOP_LEVEL_KEYS",
    "export_json",
    "persist_report_json",
    "report_persist_path",
    "report_to_payload",
    "validate_autonomicon_schema",
]
