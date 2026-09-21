"""Book lexicon loading and protection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ghostcopyeditor.checkers import run_deterministic_checkers
from ghostcopyeditor.cli import app
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.lexicon import (
    drop_lexicon_conflicts,
    find_glossary,
    load_lexicon,
)
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Location,
    Severity,
)

runner = CliRunner()


def _glossary(story: Path) -> Path:
    path = story / "canon" / "style" / "worldbuilding-glossary.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            [
                {
                    "term": "kethran",
                    "definition": "A coined rank.",
                    "aliases": ["keth'ran"],
                },
                {
                    "term": "in order to",
                    "definition": "This book's deliberate phrasing.",
                    "aliases": [],
                },
            ]
        ),
        encoding="utf-8",
    )
    return path


def _finding(excerpt: str, suggestion: str | None, rule_id: str = "llm.garbled") -> Finding:
    return Finding(
        id="",
        category=Category.GARBLED,
        severity=Severity.WARNING,
        message="Looks wrong.",
        location=Location(
            chapter_path="chapter-001.md",
            chapter_number=1,
            line_start=1,
            line_end=1,
            char_start=0,
            char_end=len(excerpt),
            excerpt=excerpt,
        ),
        engine=Engine.LLM,
        suggestion=suggestion,
        rule_id=rule_id,
        applyable=False,
        replacement=None,
    )


class TestLoadLexicon:
    def test_finds_glossary_above_chapter(self, tmp_path: Path) -> None:
        story = tmp_path / "stories" / "the-ledger-of-time"
        glossary = _glossary(story)
        chapter = story / "chapters" / "chapter-001.md"
        chapter.parent.mkdir(parents=True)
        chapter.write_text("# One\n", encoding="utf-8")
        assert find_glossary(chapter) == glossary
        lexicon = load_lexicon(story)
        assert lexicon.is_protected("Kethran")
        assert lexicon.is_protected("keth'ran")
        assert "coined rank" in lexicon.prompt_lines()[0]

    def test_missing_glossary_is_empty(self, tmp_path: Path) -> None:
        chapter = tmp_path / "chapter-001.md"
        chapter.write_text("# One\n", encoding="utf-8")
        lexicon = load_lexicon(chapter)
        assert lexicon.entries == ()
        assert lexicon.is_protected("kethran") is False


class TestProtection:
    def test_drops_rewrite_of_a_book_spelling(self, tmp_path: Path) -> None:
        lexicon = load_lexicon(_glossary(tmp_path).parent.parent.parent)
        kept = drop_lexicon_conflicts(
            [
                _finding("the kethran waited", "the captain waited"),
                _finding("the kethran waited", "the kethran stood"),
                _finding("kethran", None),
            ],
            lexicon,
        )
        assert len(kept) == 1
        assert kept[0].suggestion == "the kethran stood"

    def test_echo_and_wordiness_spare_glossary_forms(self, tmp_path: Path) -> None:
        story = tmp_path / "book"
        _glossary(story)
        lexicon = load_lexicon(story)
        text = (
            "The kethran kethran kethran stood in order to wait.\n"
        )
        chapter = Chapter("One", text, 1, story / "chapters" / "chapter-001.md")
        raw = run_deterministic_checkers(chapter, GhostCopyeditorConfig())
        kept = drop_lexicon_conflicts(raw, lexicon)
        excerpts = [f.location.excerpt.casefold() for f in kept]
        assert "kethran" not in excerpts
        assert "in order to" not in excerpts
        assert any(f.rule_id == "echo.local_repeat" for f in raw)
        assert any(f.rule_id.startswith("word.") for f in raw)


class TestCompanionUsesGlossary:
    def test_repeated_coined_word_is_not_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        story = tmp_path / "stories" / "bay-four"
        _glossary(story)
        chapter = story / "chapters" / "chapter-002.md"
        chapter.parent.mkdir(parents=True)
        chapter.write_text(
            "# Two\n\nThe kethran kethran kethran crossed the bay.\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            app,
            [
                "companion",
                str(chapter),
                "--format",
                "json",
                "--no-typesafe",
                "--no-llm",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        excerpts = [f["location"]["excerpt"].casefold() for f in data["findings"]]
        assert "kethran" not in excerpts
        assert any("Book lexicon" in warning for warning in data["warnings"])
