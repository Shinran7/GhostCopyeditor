"""Registry and deferred-rule coverage."""

from __future__ import annotations

from pathlib import Path

from ghostcopyeditor.checkers import CHECKER_REGISTRY, run_deterministic_checkers
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter


def test_registry_order_and_rule_ids() -> None:
    names = [type(c).__name__ for c in CHECKER_REGISTRY]
    assert names == [
        "MechanicsChecker",
        "StyleChecker",
        "WordinessChecker",
        "EchoChecker",
    ]
    all_ids = {rid for c in CHECKER_REGISTRY for rid in c.rule_ids}
    assert "mech.double_space" in all_ids
    assert "style.em_dash" in all_ids
    assert "echo.local_repeat" in all_ids
    assert "echo.phrase_dup" in all_ids
    # Deferred in v1 — must not ship.
    assert "mech.bare_ellipsis" not in all_ids
    assert "style.tense_hint" not in all_ids


def test_run_deterministic_checkers_emits_engine() -> None:
    chapter = Chapter(
        title="T",
        content="He  walked...\n",
        chapter_number=1,
        source_path=Path("/s/chapter-001.md"),
    )
    findings = run_deterministic_checkers(chapter, GhostCopyeditorConfig())
    assert findings
    assert all(f.engine.value == "deterministic" for f in findings)
    # Ellipsis deferred: no bare_ellipsis finding.
    assert not any(f.rule_id == "mech.bare_ellipsis" for f in findings)
