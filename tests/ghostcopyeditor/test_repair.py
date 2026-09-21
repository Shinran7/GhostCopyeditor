"""Program-safe replacement rules."""

from __future__ import annotations

from pathlib import Path

from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.llm_engine.garbled import items_to_findings
from ghostcopyeditor.repair import is_single_repair


def _chapter(text: str) -> Chapter:
    return Chapter("T", text, 1, Path("chapter-001.md"))


def test_one_character_and_one_deletion_are_repairs() -> None:
    assert is_single_repair(
        "It stanchions were iron to the root.",
        "Its stanchions were iron to the root.",
    )
    assert is_single_repair(
        "which measured the morning... No. Which measured the air.",
        "which measured the air.",
    )


def test_paraphrase_is_not_a_repair() -> None:
    assert not is_single_repair(
        "It stanchions were iron to the root.",
        "The supports ran all the way into the stone.",
    )


def test_unique_repair_fills_the_program_field() -> None:
    text = "It stanchions were iron to the root.\n"
    findings = items_to_findings(
        [
            {
                "excerpt": "It stanchions were iron to the root.",
                "message": "Dropped letter.",
                "suggestion": "Its stanchions were iron to the root.",
                "severity": "error",
            }
        ],
        _chapter(text),
    )
    assert findings[0].applyable is True
    assert findings[0].replacement == "Its stanchions were iron to the root."
    assert findings[0].metadata["expected_old"] == findings[0].location.excerpt


def test_paste_allows_deletion_and_it_to_its_only() -> None:
    from ghostcopyeditor.repair import is_pronoun_guess, is_safe_to_paste

    assert is_safe_to_paste(
        "It stanchions were iron to the root.",
        "Its stanchions were iron to the root.",
    )
    assert is_safe_to_paste("behind him behind him", "behind him")
    assert not is_safe_to_paste("She l. Down the causeway", "She laughed. Down the causeway")
    assert not is_safe_to_paste(
        "wrote while she watched her write.",
        "wrote while Faur watched.",
    )
    assert is_pronoun_guess(
        "and you planted himself at the center",
        "and you planted yourself at the center",
    )
    assert not is_pronoun_guess(
        "It stanchions were iron to the root.",
        "Its stanchions were iron to the root.",
        "Typo / garbled pronoun ('It' instead of 'Its').",
    )


def test_repeated_excerpt_is_not_applyable() -> None:
    text = "It stanchions were iron. It stanchions were iron.\n"
    findings = items_to_findings(
        [
            {
                "excerpt": "It stanchions were iron.",
                "message": "Dropped letter.",
                "suggestion": "Its stanchions were iron.",
                "severity": "error",
            }
        ],
        _chapter(text),
    )
    assert findings[0].applyable is False
    assert findings[0].replacement is None
