"""Tests for checked rewrites."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import ghostcopyeditor.llm_engine.rewrite as rw
import ghostcopyeditor.nlp.sentences as sent_mod
from ghostcopyeditor.canon import CastMember
from ghostcopyeditor.checkers import run_deterministic_checkers
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.lexicon import Lexicon, LexiconEntry
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Location,
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
GOOD = "Mara walked in and sat down, and when she looked up, she waited."


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


def _reply(*cands: str, key: str = "t1") -> str:
    return json.dumps([{"id": key, "candidates": list(cands)}])


def _run(stub: _Stub, **cfg: object) -> list[Finding]:
    ch = _chapter()
    config = GhostCopyeditorConfig(**cfg)
    findings = run_deterministic_checkers(ch, config)
    return asyncio.run(rw.run_checked_rewrites(ch, findings, stub, config))


def test_good_candidate_attached() -> None:
    stub = _Stub(_reply("Mara walked in. She sat down. She looked up. She waited a while.", GOOD))
    out = _run(stub)
    checked = [f for f in out if f.metadata.get("rewrite_checked")]
    assert {f.rule_id for f in checked} == {"rhythm.shape_run", "rhythm.same_opener_run"}
    assert all(f.suggestion == GOOD for f in checked)
    assert all(f.severity == Severity.SUGGESTION and not f.applyable for f in checked)
    assert checked[0].metadata["rewrite_original"].startswith("Mara walked in.")
    action, _ = partition_action_list(out)
    assert all(any(a is c for a in action) for c in checked)
    assert len(stub.calls) == 1


def test_all_rejected_records_reasons() -> None:
    out = _run(_Stub(_reply("Mara came in.", 'Mara walked in. "Hi." She sat. She waited.')))
    reasons = out[0].metadata["rewrite_rejected"]
    assert reasons[0] == "length"
    assert not any(f.metadata.get("rewrite_checked") for f in out)


def test_llm_error_and_bad_reply() -> None:
    assert not any("rewrite_rejected" in f.metadata for f in _run(_Stub(RuntimeError("x"))))
    assert not any("rewrite_rejected" in f.metadata for f in _run(_Stub("not json")))


def test_disabled_and_zero_cap() -> None:
    stub = _Stub(_reply(GOOD))
    _run(stub, rewrite_enabled=False)
    _run(stub, rewrite_max_per_chapter=0)
    assert stub.calls == []


def test_no_targets() -> None:
    ch = _chapter("Nobody had expected the hauler to make it back before dark.\n")
    stub = _Stub("[]")
    assert asyncio.run(rw.run_checked_rewrites(ch, [], stub, GhostCopyeditorConfig())) == []
    assert stub.calls == []


def _target(ch: Chapter, text: str, rule: str = "rhythm.shape_run") -> rw._Target:
    start = ch.content.index(text)
    return rw._Target("t1", start, start + len(text), 1, rule, (0,))


def _verify(text: str, original: str, cand: str, protected: list[str] | None = None) -> str | None:
    ch = _chapter(text)
    cfg = GhostCopyeditorConfig()
    before = run_deterministic_checkers(ch, rw._strict_cfg(cfg))
    return rw.verify_candidate(ch, _target(ch, original), cand, cfg, protected or [], before)


def test_verify_checks() -> None:
    para = "Mara walked in. She sat down.\n\nShe looked up. She waited."
    text = para + "\n"
    assert _verify(text, para, "Mara walked in and sat down. She looked up and waited.") == (
        "paragraphs"
    )
    orig = "Mara walked in. She sat down. She looked up. She waited."
    assert _verify(TEXT, orig, "Lena walked in and sat down, and when she looked up, she waited.",
                   ["Mara"]) == "names"
    spaced = "Mara walked in and sat  down, and when she looked up, she waited."
    assert _verify(TEXT, orig, spaced) == "new_problem"
    assert _verify(TEXT, orig, "") == "length"


def test_verify_variety_drop(monkeypatch: pytest.MonkeyPatch) -> None:
    values = iter([80, 40])
    monkeypatch.setattr(rw, "_scene_variety", lambda text, scene: next(values))
    orig = "Mara walked in. She sat down. She looked up. She waited."
    assert _verify(TEXT, orig, GOOD) == "variety_drop"


def test_scene_variety_none() -> None:
    assert rw._scene_variety("", 1) is None


def _finding(ch: Chapter, start: int | None, end: int | None, rule: str) -> Finding:
    loc = (
        location_from_span(ch, start, end)
        if start is not None and end is not None
        else Location(chapter_number=1, chapter_path="c.md")
    )
    return Finding(
        id="", category=Category.WEAKENER, severity=Severity.SUGGESTION, message="m",
        location=loc, engine=Engine.DETERMINISTIC, rule_id=rule,
    )


def test_targets_grouping() -> None:
    text = "Alpha one. Beta two. Gamma three. Delta four.\n\n# Head\n"
    ch = _chapter(text)
    a = text.index("Beta")
    b = text.index("Gamma")
    head = text.index("# Head")
    findings = [
        _finding(ch, 0, text.index("Gamma") + 5, "rhythm.shape_run"),  # Alpha..Gamma
        _finding(ch, a, a + 4, "weak.qualifier"),  # inside: joins
        _finding(ch, b, text.index("Delta") + 5, "weak.filter_word"),  # partial: skipped
        _finding(ch, None, None, "weak.qualifier"),  # no offsets
        _finding(ch, head, head + 3, "weak.qualifier"),  # not in a sentence
        _finding(ch, 0, 5, "mech.double_space"),  # not a target
    ]
    targets = rw._targets(findings, ch, 8)
    assert len(targets) == 1
    assert sorted(targets[0].indices) == [0, 1]
    assert rw._targets(findings, ch, 0) == []


def test_parse() -> None:
    assert rw._parse("```json\n" + _reply("a", "b", "c") + "\n```") == {"t1": ["a", "b"]}
    assert rw._parse("note: " + _reply("a") + " end") == {"t1": ["a"]}
    assert rw._parse("[broken") == {}
    assert rw._parse("x [1, oops] y") == {}
    assert rw._parse('{"id": "t1"}') == {}
    assert rw._parse('[1, {"id": 2, "candidates": []}, {"id": "t2", "candidates": ["", 3]}]') == {
        "t2": []
    }


def test_rules_in_skips_unplaced() -> None:
    ch = _chapter()
    assert rw._rules_in([_finding(ch, None, None, "weak.x")], 0, 10) == set()


def test_user_prompt_includes_book_and_cast() -> None:
    ch = _chapter()
    book = Lexicon(entries=[LexiconEntry(term="Hauler", definition="", aliases=())])
    cast = (CastMember(name="Mara", pronouns="she/her", family=None, tokens=("Mara",)),)
    target = _target(ch, "Mara walked in.")
    prompt = rw._user_prompt(ch, 9, [target], book, cast)
    assert "Book terms" in prompt
    assert "Mara: she/her" in prompt
    assert '"id": "t1"' in prompt


def test_pipeline_wires_rewrites() -> None:
    stub = _Stub(_reply(GOOD))
    out = asyncio.run(
        run_chapter_pipeline(
            _chapter(), cfg=GhostCopyeditorConfig(), llm=stub, llm_enabled=True
        )
    )
    assert any(f.metadata.get("rewrite_checked") for f in out)
