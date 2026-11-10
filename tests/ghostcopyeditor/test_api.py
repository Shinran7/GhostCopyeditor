"""Tests for the in-process library API."""

from __future__ import annotations

import asyncio
from pathlib import Path

import ghostcopyeditor.api as api_mod
from ghostcopyeditor.api import API_VERSION, ChapterCheck, check_chapter
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.models.finding import Category
from ghostcopyeditor.pipeline.runner import drop_skipped_rules

TEXT = (
    "She walked in  to the room. In order to see, she lit a lamp.\n\n"
    "---\n\n"
    "The door door shut. Rain fell all night.\n"
)


def test_check_chapter_sync() -> None:
    result = check_chapter(TEXT, chapter_number=3, path="ch3.md")
    assert isinstance(result, ChapterCheck)
    assert result.api_version == API_VERSION == 1
    assert [s["scene"] for s in result.scenes] == [1, 2]
    for f in result.findings + result.may_look:
        assert f.location.chapter_number == 3
    assert all(f.category != Category.ECHO for f in result.findings)
    d = result.to_dict()
    assert d["api_version"] == 1
    assert len(d["findings"]) == len(result.findings)


def test_skip_rules_prefix() -> None:
    full = check_chapter(TEXT)
    rules = {f.rule_id for f in full.findings + full.may_look if f.rule_id}
    assert rules
    prefix = sorted(rules)[0].split(".")[0] + "."
    cut = check_chapter(TEXT, skip_rules=[prefix])
    left = {f.rule_id for f in cut.findings + cut.may_look if f.rule_id}
    assert not any(r.startswith(prefix) for r in left)


def test_inside_running_loop() -> None:
    async def inner() -> ChapterCheck:
        return check_chapter(TEXT)

    assert asyncio.run(inner()).scenes


def test_story_dir_and_warning(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "ghostcopyeditor.nlp.missing_predicate_skip_warning", lambda cfg: "no nlp"
    )
    cfg = GhostCopyeditorConfig(skip_rules=["x."])
    result = check_chapter(TEXT, story_dir=tmp_path, config=cfg)
    assert result.warnings == ["no nlp"]


def test_drop_skipped_rules_empty() -> None:
    assert drop_skipped_rules([], [""]) == []


def test_exports() -> None:
    assert set(api_mod.__all__) >= {"check_chapter", "check_chapter_async"}
