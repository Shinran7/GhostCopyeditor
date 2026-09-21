"""Package export smoke for ghostcopyeditor.report."""

from __future__ import annotations

from ghostcopyeditor import report


def test_report_package_exports() -> None:
    assert hasattr(report, "export_json")
    assert hasattr(report, "persist_report_json")
    assert hasattr(report, "render_report")
    assert hasattr(report, "validate_autonomicon_schema")
