"""Safe deterministic --apply writer.

Only whitelisted deterministic applyable findings are written. Locations in the
report stay pre-apply; successful writes set ``metadata.applied``.
"""

from __future__ import annotations

from pathlib import Path

from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import Engine, Finding, Severity

_SEVERITY_RANK = {
    Severity.ERROR: 3,
    Severity.WARNING: 2,
    Severity.SUGGESTION: 1,
    Severity.INFO: 0,
}


def expected_old_text(finding: Finding) -> str | None:
    """Return the text that must still occupy the span before a write."""
    meta = finding.metadata.get("expected_old")
    if isinstance(meta, str):
        return meta
    if finding.location.char_start is None or finding.location.char_end is None:
        return None
    # Fall back to excerpt only when it equals the full span length contract.
    return finding.location.excerpt or None


def is_apply_candidate(finding: Finding) -> bool:
    return (
        finding.engine == Engine.DETERMINISTIC
        and finding.applyable
        and finding.replacement is not None
        and finding.location.char_start is not None
        and finding.location.char_end is not None
        and expected_old_text(finding) is not None
    )


def refuse_overlapping_applyable(findings: list[Finding]) -> tuple[list[Finding], list[str]]:
    """Clear applyable on overlapping spans; prefer higher severity, then rule_id."""
    candidates = [f for f in findings if is_apply_candidate(f)]
    warnings: list[str] = []

    ordered = sorted(
        candidates,
        key=lambda f: (
            -_SEVERITY_RANK.get(f.severity, 0),
            f.rule_id or "",
            f.location.char_start or 0,
        ),
    )
    kept: list[Finding] = []
    for finding in ordered:
        start = finding.location.char_start
        end = finding.location.char_end
        assert start is not None
        assert end is not None
        conflict = False
        for prior in kept:
            p_start = prior.location.char_start
            p_end = prior.location.char_end
            assert p_start is not None
            assert p_end is not None
            if start < p_end and p_start < end:
                conflict = True
                finding.applyable = False
                warnings.append(
                    f"Skipped overlapping applyable span for {finding.rule_id} "
                    f"at {start}:{end} (kept {prior.rule_id})."
                )
                break
        if not conflict:
            kept.append(finding)
    return findings, warnings


def apply_to_content(
    content: str, findings: list[Finding]
) -> tuple[str, int, list[str]]:
    """Apply safe fixes in reverse offset order. Mutates finding metadata."""
    _, overlap_warnings = refuse_overlapping_applyable(findings)
    warnings = list(overlap_warnings)

    writable = [
        f
        for f in findings
        if is_apply_candidate(f) and f.applyable
    ]
    writable.sort(
        key=lambda f: (f.location.char_start or 0, f.location.char_end or 0),
        reverse=True,
    )

    text = content
    applied = 0
    for finding in writable:
        start = finding.location.char_start
        end = finding.location.char_end
        assert start is not None
        assert end is not None
        expected = expected_old_text(finding)
        assert expected is not None
        actual = text[start:end]
        if actual != expected:
            finding.applyable = False
            warnings.append(
                f"Apply re-verify failed for {finding.rule_id} at {start}:{end}; "
                "left unchanged."
            )
            continue
        replacement = finding.replacement
        assert replacement is not None
        text = text[:start] + replacement + text[end:]
        finding.metadata["applied"] = True
        applied += 1
    return text, applied, warnings


def apply_to_chapter(
    chapter: Chapter, findings: list[Finding]
) -> tuple[int, list[str]]:
    """Write UTF-8 in place for one chapter. Returns applied_count and warnings."""
    chapter_findings = [
        f for f in findings if f.location.chapter_number == chapter.chapter_number
    ]
    new_text, applied, warnings = apply_to_content(chapter.content, chapter_findings)
    if applied:
        path = Path(chapter.source_path)
        path.write_text(new_text, encoding="utf-8")
        chapter.content = new_text
    return applied, warnings


def apply_findings(
    chapters: list[Chapter], findings: list[Finding]
) -> tuple[int, list[str]]:
    """Apply whitelisted fixes across chapters. Report coords stay pre-apply."""
    total = 0
    warnings: list[str] = []
    for chapter in chapters:
        applied, chapter_warnings = apply_to_chapter(chapter, findings)
        total += applied
        warnings.extend(chapter_warnings)
    return total, warnings


__all__ = [
    "apply_findings",
    "apply_to_chapter",
    "apply_to_content",
    "expected_old_text",
    "is_apply_candidate",
    "refuse_overlapping_applyable",
]
