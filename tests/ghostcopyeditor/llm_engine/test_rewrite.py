"""Tests for checked passage rewrites."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import ghostcopyeditor.llm_engine.rewrite as rw
import ghostcopyeditor.nlp.sentences as sent_mod
from ghostcopyeditor.api import check_chapter
from ghostcopyeditor.canon import CastMember
from ghostcopyeditor.checkers import run_deterministic_checkers
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.lexicon import Lexicon, LexiconEntry
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Severity,
    location_from_span,
)
from ghostcopyeditor.models.report import partition_action_list
from ghostcopyeditor.nlp.sentences import clear_cache
from ghostcopyeditor.pipeline.runner import run_chapter_pipeline

TEXT = (
    "When the storm broke over the ridge, the crews came down from the pylons "
    "in a long, ragged line. Mara walked in. She sat down. She looked up. "
    "She waited.\n\n"
    "Nobody had expected the hauler to make it back before dark, and yet "
    "there it was.\n"
)
GOOD = (
    "When the storm broke over the ridge, the crews came down from the pylons "
    "in a long, ragged line. Mara walked in and sat down, and when she looked "
    "up, she waited."
)
KEPT = {"facts": [{"fact": "Mara sits and waits", "status": "kept"}], "added": [],
        "after_ok": True, "wording": ["merged the short beats"]}


@pytest.fixture(autouse=True)
def _fresh() -> None:
    if sent_mod.get_nlp() is None:
        pytest.skip("spaCy model not installed")
    clear_cache()
    yield
    clear_cache()


class _Stub:
    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply
        self.calls: list[Any] = []

    async def ainvoke(self, messages: list[Any]) -> Any:
        self.calls.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(content=self.reply)


def _chapter(text: str = TEXT) -> Chapter:
    return Chapter(title="t", content=text, chapter_number=1, source_path=Path("c.md"))


def _draft(edit: str = GOOD, **extra: object) -> str:
    return json.dumps({"purpose": "Mara arrives and waits.", "facts": [],
                       "cuts": ["merged four short beats"], "edit": edit, **extra})


def _run(writer: _Stub, checker: _Stub, **cfg: object) -> list[Finding]:
    ch = _chapter()
    config = GhostCopyeditorConfig(**cfg)
    findings = run_deterministic_checkers(ch, config)
    return asyncio.run(rw.run_passage_rewrites(ch, findings, writer, checker, config))


def _passages(out: list[Finding]) -> list[Finding]:
    return [f for f in out if f.rule_id == "rewrite.passage"]


def _rejected(out: list[Finding]) -> list[str]:
    return next(f.metadata["rewrite_rejected"] for f in out if "rewrite_rejected" in f.metadata)


def test_checked_edit_becomes_passage_finding() -> None:
    writer, checker = _Stub(_draft()), _Stub(json.dumps(KEPT))
    out = _run(writer, checker)
    (edit,) = _passages(out)
    assert edit.category == Category.REWRITE
    assert edit.severity == Severity.SUGGESTION
    assert edit.engine == Engine.LLM
    assert not edit.applyable
    assert edit.suggestion == GOOD
    assert edit.message == "Passage edit: Mara arrives and waits."
    assert edit.metadata["rewrite_start"] == 0
    assert edit.metadata["rewrite_original"] == TEXT.split("\n\n")[0]
    assert edit.metadata["wording"] == ["merged the short beats"]
    assert edit.metadata["cuts"] == ["merged four short beats"]
    assert "rhythm.shape_run" in edit.metadata["target_rules"]
    action, _ = partition_action_list(out)
    assert edit in action
    writer_prompt = writer.calls[0][1].content
    assert "PASSAGE:" in writer_prompt
    assert "AFTER:\nNobody had expected" in writer_prompt
    assert "NOTES:" in writer_prompt
    assert "EDITED:" in checker.calls[0][1].content


@pytest.mark.parametrize(
    ("report", "reason"),
    [
        ({**KEPT, "facts": [{"fact": "Mara waits", "status": "lost"}]}, "fact lost"),
        ({**KEPT, "added": ["a lamp"]}, "fact added"),
        ({**KEPT, "after_ok": False, "after_note": "x"}, "after text breaks"),
        ({**KEPT, "facts": []}, "checker listed no facts"),
    ],
)
def test_checker_rejects(report: dict[str, Any], reason: str) -> None:
    out = _run(_Stub(_draft()), _Stub(json.dumps(report)))
    assert not _passages(out)
    assert any(r.startswith(reason) for r in _rejected(out))


@pytest.mark.parametrize(
    ("writer", "checker", "reason"),
    [
        (_draft(), "not json", "checker_unreadable"),
        ("nonsense", json.dumps(KEPT), "writer_unreadable"),
        (_draft(TEXT.split("\n\n")[0]), json.dumps(KEPT), "unchanged"),
        (_draft("Mara sat."), json.dumps(KEPT), "length"),
    ],
)
def test_bad_replies_rejected(writer: str, checker: str, reason: str) -> None:
    out = _run(_Stub(writer), _Stub(checker))
    assert _rejected(out) == [reason]


def test_model_errors_rejected() -> None:
    out = _run(_Stub(RuntimeError("down")), _Stub(json.dumps(KEPT)))
    assert _rejected(out) == ["writer_failed"]
    out = _run(_Stub(_draft()), _Stub(RuntimeError("down")))
    assert _rejected(out) == ["checker_failed"]


def test_disabled_zero_cap_and_no_targets() -> None:
    writer, checker = _Stub(_draft()), _Stub(json.dumps(KEPT))
    assert not _passages(_run(writer, checker, rewrite_enabled=False))
    assert not _passages(_run(writer, checker, rewrite_max_per_chapter=0))
    assert asyncio.run(
        rw.run_passage_rewrites(_chapter(), [], writer, checker, GhostCopyeditorConfig())
    ) == []
    assert writer.calls == []


def _unit(ch: Chapter, para: int = 0) -> Any:
    start, end = rw.paragraph_spans(ch.content)[para]
    return rw._Unit(start, end, para, para, ())


def _verify(edit: str, protected: list[str] | None = None, text: str = TEXT) -> str | None:
    ch = _chapter(text)
    cfg = GhostCopyeditorConfig()
    before = run_deterministic_checkers(ch, rw._strict_cfg(cfg))
    return rw.verify_edit(ch, _unit(ch), edit, cfg, protected or [], before)


def test_verify_edit() -> None:
    assert _verify(GOOD) is None
    assert _verify("   ") == "empty"
    assert _verify(GOOD + " " + GOOD) == "length"
    assert _verify(GOOD + "\n\nShe waited longer.") == "paragraphs"
    assert _verify(GOOD.replace("Mara", "She"), ["Mara"]) == "names"
    assert _verify(GOOD, ["Mara"]) is None
    assert _verify(GOOD.replace("she waited", "she very very really waited")) == "new_problem"
    quoted = 'Mara said, "Wait here," and sat down by the long cold window to wait.\n'
    assert _verify('Mara said, "Wait," and sat down by the long cold window to wait.',
                   text=quoted) == "dialogue"


def test_units_pair_neighbours_and_cap() -> None:
    text = "\n\n".join(f"Para {i} has some words in it." for i in range(6)) + "\n"
    ch = _chapter(text)
    paras = rw.paragraph_spans(text)

    def note(para: int, rule: str = "weak.filter") -> Finding:
        start = paras[para][0]
        return Finding(id="", category=Category.WEAKENER, severity=Severity.INFO,
                       message="m", location=location_from_span(ch, start, start + 4),
                       engine=Engine.DETERMINISTIC, rule_id=rule)

    found = [note(0), note(1), note(2), note(4), note(4, "hollow.image"),
             note(5, "echo.local_repeat")]
    units = rw._units(found, ch, limit=10)
    assert [(u.first, u.last) for u in units] == [(0, 1), (2, 2), (4, 4)]
    assert units[0].indices == (0, 1)
    top = rw._units(found, ch, limit=1)
    assert [(u.first, u.last) for u in top] == [(0, 1)]


def test_units_skip_headings() -> None:
    ch = _chapter("# Chapter One\n\nBody text here.\n")
    f = Finding(id="", category=Category.WEAKENER, severity=Severity.INFO, message="m",
                location=location_from_span(ch, 0, 5), engine=Engine.DETERMINISTIC,
                rule_id="weak.filter")
    assert rw._units([f], ch, limit=5) == []


def test_parse_and_judge_helpers() -> None:
    assert rw._parse_object('```json\n{"edit": "x"}\n```') == {"edit": "x"}
    assert rw._parse_object("[1, 2]") is None
    assert rw._parse_object("{bad json}") is None
    assert rw._str_list("nope") == []
    reasons, clean = rw.judge_continuity({"facts": [{"fact": "a"}, "junk"]})
    assert reasons == ["fact unclear: a"]
    assert clean["facts"][0]["status"] == ""
    assert rw._rules_in([Finding(id="", category=Category.WEAKENER, severity=Severity.INFO,
                                 message="m", location=location_from_span(_chapter(), 0, 0),
                                 engine=Engine.DETERMINISTIC)], 0, 5) == set()


def test_writer_prompt_includes_book_and_cast() -> None:
    ch = _chapter()
    book = Lexicon(entries=[LexiconEntry(term="Hauler", definition="", aliases=())])
    cast = (CastMember(name="Mara", pronouns="she/her", family=None, tokens=("Mara",)),)
    prompt = rw._writer_prompt(ch, _unit(ch, 1), ["note one"], book, cast)
    assert "BOOK TERMS" in prompt
    assert "Mara: she/her" in prompt
    assert "BEFORE:\nWhen the storm" in prompt
    assert "- note one" in prompt


def test_pipeline_needs_writer_and_checker() -> None:
    cfg = GhostCopyeditorConfig(hollow_enabled=False)
    main = _Stub("[]")
    out = asyncio.run(run_chapter_pipeline(_chapter(), cfg=cfg, llm=main, llm_enabled=True))
    assert not _passages(out)
    roles = SimpleNamespace(rewrite_writer=_Stub(_draft()), rewrite_checker=_Stub(json.dumps(KEPT)))
    out = asyncio.run(
        run_chapter_pipeline(_chapter(), cfg=cfg, llm=main, llm_enabled=True, role_llms=roles)
    )
    assert _passages(out)


def test_api_rewrites() -> None:
    cfg = GhostCopyeditorConfig(hollow_enabled=False)
    result = check_chapter(TEXT, config=cfg, rewrites=True)
    assert any("Rewrites skipped" in w for w in result.warnings)
    roles = SimpleNamespace(rewrite_writer=_Stub(_draft()), rewrite_checker=_Stub(json.dumps(KEPT)))
    result = check_chapter(TEXT, config=cfg, rewrites=True, role_llms=roles)
    assert any(f.rule_id == "rewrite.passage" for f in result.findings)


def test_figurative_loss_is_a_wording_note() -> None:
    report = {**KEPT, "facts": [*KEPT["facts"],
                                {"fact": "a smell with no opinion", "status": "lost",
                                 "literal": False}]}
    out = _run(_Stub(_draft()), _Stub(json.dumps(report)))
    (edit,) = _passages(out)
    assert "lost: a smell with no opinion" in edit.metadata["wording"]
    assert all(f["literal"] for f in edit.metadata["facts"])
    only_figurative = {**KEPT, "facts": [{"fact": "x", "status": "kept", "literal": False}]}
    out = _run(_Stub(_draft()), _Stub(json.dumps(only_figurative)))
    assert _rejected(out) == ["checker listed no facts"]


def test_rejected_edit_is_kept_for_review() -> None:
    out = _run(_Stub(_draft()), _Stub(json.dumps({**KEPT, "added": ["a lamp"]})))
    assert any(f.metadata.get("rewrite_rejected_edit") == GOOD for f in out)
