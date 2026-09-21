"""Terminal and JSON report emitters for Autonomicon-stable output."""

from ghostcopyeditor.report.json_export import (
    REQUIRED_CHAPTER_KEYS,
    REQUIRED_SUMMARY_KEYS,
    REQUIRED_TOP_LEVEL_KEYS,
    export_json,
    persist_report_json,
    report_persist_path,
    report_to_payload,
    validate_autonomicon_schema,
)
from ghostcopyeditor.report.terminal import render_report

__all__ = [
    "REQUIRED_CHAPTER_KEYS",
    "REQUIRED_SUMMARY_KEYS",
    "REQUIRED_TOP_LEVEL_KEYS",
    "export_json",
    "persist_report_json",
    "render_report",
    "report_persist_path",
    "report_to_payload",
    "validate_autonomicon_schema",
]
