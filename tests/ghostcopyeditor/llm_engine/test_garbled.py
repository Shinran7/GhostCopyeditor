"""Colocated garbled engine tests (forward-coverage twin of tests/test_llm_garbled.py)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.llm_engine.garbled import (
    items_to_findings,
    parse_garbled_response,
    run_llm_garbled,
)
from ghostcopyeditor.models.finding import Engine


class _JsonStub(BaseChatModel):
    payload: str = "[]"

    @property
    def _llm_type(self) -> str:
        return "stub"

    def _generate(self, messages: list[BaseMessage], **kwargs: object) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=self.payload))]
        )

    async def _agenerate(
        self, messages: list[BaseMessage], **kwargs: object
    ) -> ChatResult:
        return self._generate(messages, **kwargs)


def test_parse_and_findings_round_trip() -> None:
    chapter = Chapter(
        title="T",
        content="Then asdfjkl wreckage.\n",
        chapter_number=1,
        source_path=Path("/story/chapters/chapter-001.md"),
    )
    items = parse_garbled_response(
        json.dumps(
            [
                {
                    "excerpt": "asdfjkl wreckage",
                    "message": "Keyboard smash.",
                    "suggestion": "Then silence.",
                    "severity": "warning",
                }
            ]
        )
    )
    findings = items_to_findings(items, chapter)
    assert len(findings) == 1
    assert findings[0].engine == Engine.LLM
    assert findings[0].applyable is False


def test_run_llm_garbled_with_stub_json() -> None:
    chapter = Chapter(
        title="T",
        content="Broken sentence the.\n",
        chapter_number=2,
        source_path=Path("/story/chapters/chapter-002.md"),
    )
    llm = _JsonStub(
        payload=json.dumps(
            [
                {
                    "excerpt": "Broken sentence the.",
                    "message": "Dropped words.",
                    "suggestion": "The sentence was broken.",
                    "severity": "warning",
                }
            ]
        )
    )
    findings = asyncio.run(
        run_llm_garbled(chapter, [], llm, GhostCopyeditorConfig())
    )
    assert len(findings) == 1
    assert findings[0].suggestion == "The sentence was broken."
