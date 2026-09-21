"""Cast pronouns and names from canon/characters."""

from __future__ import annotations

import json
from pathlib import Path

from ghostcopyeditor.canon import apply_cast, load_cast, named_in
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Location,
    Severity,
)


def _member_file(folder: Path, slug: str, name: str, pronouns: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{slug}.json").write_text(
        json.dumps({"slug": slug, "name": name, "pronouns": pronouns}),
        encoding="utf-8",
    )


def _finding(excerpt: str, suggestion: str, message: str) -> Finding:
    return Finding(
        id="",
        category=Category.GARBLED,
        severity=Severity.WARNING,
        message=message,
        location=Location(
            chapter_number=1,
            chapter_path="chapter-001.md",
            excerpt=excerpt,
        ),
        engine=Engine.LLM,
        suggestion=suggestion,
        rule_id="llm.garbled",
        applyable=True,
        replacement=suggestion,
    )


def _cast(tmp_path: Path):
    story = tmp_path / "stories" / "shatterbound"
    folder = story / "canon" / "characters"
    _member_file(folder, "ilya-fenwick", "Ilya Fenwick", "he/him")
    _member_file(folder, "pedra-morn", "Pedra Morn", "she/her")
    _member_file(folder, "batbayar-hallow", "Batbayar Hallow", "she/her")
    return load_cast(story / "chapters" / "chapter-001.md")


def test_surrounding_prose_finds_excerpt_without_offsets() -> None:
    from ghostcopyeditor.ingestion import Chapter
    from ghostcopyeditor.typesafe.garbled_review import surrounding_prose

    chapter = Chapter("T", "Before. It stanchions were iron. After.", 1, Path("c.md"))
    finding = _finding("It stanchions were iron.", "Its stanchions were iron.", "Typo.")
    text = surrounding_prose(chapter, finding)
    assert "Before." in text
    assert "After." in text


def test_prompt_includes_cast_and_lexicon() -> None:
    from ghostcopyeditor.llm_engine.prompts import build_garbled_user_prompt

    text = build_garbled_user_prompt(
        "Hello.",
        chapter_number=1,
        lexicon_lines=["- kin-sign: an oath tell"],
        cast_lines=["- Ilya Fenwick: he/him"],
    )
    assert "kin-sign" in text
    assert "Ilya Fenwick: he/him" in text


def test_blank_pronoun_label_has_no_family() -> None:
    from ghostcopyeditor.canon import _family_for_label

    assert _family_for_label("") is None
    assert _family_for_label("he/him") is not None


def test_loads_pronouns_and_unique_names(tmp_path: Path) -> None:
    cast = _cast(tmp_path)
    by_name = {member.name: member for member in cast}
    assert by_name["Ilya Fenwick"].pronouns == "he/him"
    assert "Ilya" in by_name["Ilya Fenwick"].tokens
    short = tmp_path / "stories" / "short" / "canon" / "characters"
    _member_file(short, "bo-smith", "Bo Smith", "he/him")
    assert "Bo" in load_cast(short.parent.parent)[0].tokens
    assert named_in("Ilya held her sleeve.", cast)[0].name == "Ilya Fenwick"


def test_keeps_pronoun_note_only_when_it_matches_the_file(tmp_path: Path) -> None:
    cast = _cast(tmp_path)
    toward = _finding(
        "Ilya held her sleeve.",
        "Ilya held his sleeve.",
        "Pronoun mismatch.",
    )
    away = _finding(
        "Ilya held his sleeve.",
        "Ilya held her sleeve.",
        "Pronoun mismatch.",
    )
    kept = apply_cast([toward, away], cast)
    assert kept == [toward]
    assert kept[0].applyable is False
    assert kept[0].metadata["cast_pronouns"] == "he/him"


def test_drops_a_fix_that_erases_a_canon_name(tmp_path: Path) -> None:
    cast = _cast(tmp_path)
    finding = _finding(
        "Batbayar the old salt-margins",
        "Along the old salt-margins",
        "Extraneous word Batbayar.",
    )
    assert apply_cast([finding], cast) == []


def test_character_file_and_chapter_mixes_are_findings(tmp_path: Path) -> None:
    from ghostcopyeditor.canon import canon_file_findings, chapter_pronoun_findings
    from ghostcopyeditor.ingestion import Chapter

    story = tmp_path / "stories" / "shatterbound"
    folder = story / "canon" / "characters"
    _member_file(folder, "ilya-fenwick", "Ilya Fenwick", "he/him")
    path = folder / "ilya-fenwick.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["backstory"] = "She thinks she can bargain if she remains polite."
    path.write_text(json.dumps(raw), encoding="utf-8")
    _member_file(folder, "ysolde-kestrel", "Ysolde Kestrel", "she/her")
    file_notes = canon_file_findings(story)
    assert any(note.metadata["cast_name"] == "Ilya Fenwick" for note in file_notes)
    assert all(note.rule_id == "canon.pronoun_file" for note in file_notes)

    chapter = Chapter(
        "Twelve",
        "Ilya sat with his bread while Ysolde crossed to her, where the girl waited.\n",
        12,
        story / "chapters" / "chapter-012.md",
    )
    prose = chapter_pronoun_findings(chapter, load_cast(story))
    assert len(prose) == 1
    assert prose[0].rule_id == "canon.pronoun_prose"
    assert "girl" in prose[0].message
    assert prose[0].applyable is False
    quiet = Chapter(
        "Twelve",
        "Ilya sat with his bread and ate it.\n",
        12,
        story / "chapters" / "chapter-012.md",
    )
    assert chapter_pronoun_findings(quiet, load_cast(story)) == []
    boy = Chapter(
        "Two",
        "Ysolde sent the boy ahead with the mule.\n",
        2,
        story / "chapters" / "chapter-002.md",
    )
    boy_hits = chapter_pronoun_findings(boy, load_cast(story))
    assert len(boy_hits) == 1
    assert boy_hits[0].metadata["cast_name"] == "Ysolde Kestrel"


def test_it_to_its_is_not_a_cast_guess(tmp_path: Path) -> None:
    cast = _cast(tmp_path)
    finding = _finding(
        "It stanchions were iron.",
        "Its stanchions were iron.",
        "Typo / garbled pronoun ('It' instead of 'Its').",
    )
    kept = apply_cast([finding], cast)
    assert len(kept) == 1
    assert kept[0].replacement == "Its stanchions were iron."
