"""Tests for the hollow-imagery judge."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.llm_engine.hollow import (
    _phrase_span,
    build_hollow_user_prompt,
    parse_hollow_response,
    run_hollow_judge,
)
from ghostcopyeditor.models.finding import Category
from ghostcopyeditor.models.report import partition_action_list
from ghostcopyeditor.nlp.sentences import clear_cache

TEXT = (
    "Coolant knocked once in the pipe and gurgled on. Nobody filled\nthe knock.\n\n"
    "Harbor tar and cold leather rose, a smell with no opinion.\n"
)


class _Stub:
    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply
        self.calls: list[Any] = []

    async def ainvoke(self, messages: list[Any]) -> Any:
        self.calls.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(content=self.reply)


def _run(reply: str | Exception, text: str = TEXT, **cfg: object) -> tuple[list[Any], _Stub]:
    clear_cache()
    ch = Chapter(title="t", content=text, chapter_number=1, source_path=Path("c.md"))
    stub = _Stub(reply)
    out = asyncio.run(run_hollow_judge(ch, stub, GhostCopyeditorConfig(**cfg)))
    return out, stub


def test_hollow_lines_become_notes() -> None:
    reply = json.dumps(
        [
            {"n": 1, "label": "HOLLOW", "phrase": "Nobody filled the knock",
             "why": "a knock is a sound."},
            {"n": 2, "label": "works", "phrase": "", "why": "fine"},
        ]
    )
    out, stub = _run("```json\n" + reply + "\n```")
    assert len(out) == 1
    f = out[0]
    assert f.category == Category.HOLLOW
    assert f.rule_id == "hollow.image"
    assert TEXT[f.location.char_start : f.location.char_end] == "Nobody filled\nthe knock"
    assert f.message == "Hollow image “Nobody filled the knock”. a knock is a sound."
    assert f.metadata["pattern"] == "narrow"
    assert "CANDIDATES:\n1. Nobody filled the knock." in stub.calls[0][1].content
    action, may_look = partition_action_list(out)
    assert not action
    assert may_look == out


def test_phrase_not_found_uses_sentence() -> None:
    reply = json.dumps([{"n": 2, "label": "HOLLOW", "phrase": "not here", "why": ""}])
    (f,), _ = _run(reply)
    assert f.location.excerpt == "Harbor tar and cold leather rose, a smell with no opinion."
    assert f.message.endswith("opinion”.")


def test_off_paths() -> None:
    assert _run("[]", hollow_enabled=False)[0] == []
    assert _run("[]", hollow_max_candidates=0)[0] == []
    assert _run("[]", text="She opened the door.\n")[0] == []
    assert _run(RuntimeError("down"))[0] == []
    assert _run("not json")[0] == []


def test_parse_and_helpers() -> None:
    assert parse_hollow_response("[oops]") == {}
    assert parse_hollow_response('{"n": 1}') == {}
    got = parse_hollow_response('[{"n": 1, "label": "hollow"}, {"n": "x"}, 3]')
    assert got == {1: {"label": "HOLLOW", "phrase": "", "why": ""}}
    assert _phrase_span("abc", "") is None
    ch = Chapter(title="t", content="x", chapter_number=1, source_path=Path("c.md"))
    assert build_hollow_user_prompt(ch, ["a\nb"]).endswith("1. a b")
