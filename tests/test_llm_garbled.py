"""Design PR5 path for LLM garbled tests.

Canonical colocated cases live under ``tests/ghostcopyeditor/llm_engine/``.
Integration and CLI cases remain in this module.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from typer.testing import CliRunner

from ghostcopyeditor.checkers.apply import apply_to_content, is_apply_candidate
from ghostcopyeditor.cli import app
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.llm import get_llm, message_text
from ghostcopyeditor.llm_engine.garbled import (
    items_to_findings,
    parse_garbled_response,
    run_llm_garbled,
)
from ghostcopyeditor.models.finding import Category, Engine, Severity
from ghostcopyeditor.pipeline.runner import run_chapter_pipeline

runner = CliRunner()


def test_design_llm_garbled_suite_present() -> None:
    root = Path(__file__).parent / "ghostcopyeditor" / "llm_engine"
    assert (root / "test_garbled.py").is_file()
    assert (root / "test_prompts.py").is_file()
    assert (root / "test___init__.py").is_file()


class JsonStubChatModel(BaseChatModel):
    """Stub that returns fixed JSON for garbled detection tests."""

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


def _chapter(text: str, *, num: int = 1) -> Chapter:
    return Chapter(
        title="T",
        content=text,
        chapter_number=num,
        source_path=Path(f"/story/chapters/chapter-{num:03d}.md"),
    )


class TestMessageText:
    def test_string_and_parts(self) -> None:
        assert message_text("  hi  ") == "hi"
        assert message_text([{"text": "a"}, "b"]) == "a\nb"
        assert message_text(None) == ""


class TestParseGarbled:
    def test_plain_list(self) -> None:
        raw = json.dumps(
            [
                {
                    "excerpt": "He walked the",
                    "message": "Truncated mid-clause.",
                    "suggestion": "He walked the road.",
                    "severity": "warning",
                }
            ]
        )
        items = parse_garbled_response(raw)
        assert len(items) == 1
        assert items[0]["excerpt"] == "He walked the"

    def test_fenced_and_wrapped(self) -> None:
        raw = '```json\n{"findings": [{"excerpt": "x", "message": "m"}]}\n```'
        items = parse_garbled_response(raw)
        assert len(items) == 1

    def test_non_list_object_returns_empty(self) -> None:
        assert parse_garbled_response('{"ok": true}') == []

    def test_trailing_prose_array(self) -> None:
        raw = 'Here you go:\n[{"excerpt": "x", "message": "m"}]\nThanks'
        assert len(parse_garbled_response(raw)) == 1

    def test_invalid_returns_empty(self) -> None:
        assert parse_garbled_response("not json") == []
        assert parse_garbled_response("") == []


class TestItemsToFindings:
    def test_anchors_and_unanchored(self) -> None:
        chapter = _chapter("He walked the road.\nThen asdfjkl wreckage.\n")
        items = [
            {
                "excerpt": "asdfjkl wreckage",
                "message": "Keyboard smash.",
                "suggestion": "Then silence.",
                "severity": "error",
            },
            {
                "excerpt": "NOT IN CHAPTER",
                "message": "Missing span.",
                "suggestion": "fixed",
                "severity": "warning",
            },
            {"excerpt": "", "message": ""},
            {
                "excerpt": "asdfjkl wreckage",
                "message": "",
                "suggestion": None,
                "severity": "weird",
            },
        ]
        findings = items_to_findings(items, chapter)
        assert len(findings) == 3
        assert findings[0].engine == Engine.LLM
        assert findings[0].category == Category.GARBLED
        assert findings[0].applyable is False
        assert findings[0].suggestion == "Then silence."
        assert findings[0].severity == Severity.ERROR
        assert findings[0].location.char_start is not None
        assert findings[1].metadata.get("unanchored") is True
        assert findings[2].message.startswith("Passage appears")
        assert findings[2].severity == Severity.WARNING

    def test_repeated_excerpt_anchors_the_later_copy(self) -> None:
        chapter = _chapter("One road here.\nAnother road here.\n")
        items = [
            {"excerpt": "road here", "message": "First.", "severity": "warning"},
            {"excerpt": "road here", "message": "Second.", "severity": "warning"},
        ]
        findings = items_to_findings(items, chapter)
        assert findings[0].location.char_start < findings[1].location.char_start


class TestRunLlmGarbled:
    def test_stub_json_produces_findings(self) -> None:
        chapter = _chapter("Broken sentence the.\n")
        llm = JsonStubChatModel(
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
        assert findings[0].applyable is False

    def test_default_stub_returns_no_findings(self) -> None:
        chapter = _chapter("Clean prose.\n")
        llm = get_llm("stub")
        findings = asyncio.run(
            run_llm_garbled(chapter, [], llm, GhostCopyeditorConfig())
        )
        assert findings == []

    def test_ainvoke_failure_returns_empty(self) -> None:
        class _Boom(BaseChatModel):
            @property
            def _llm_type(self) -> str:
                return "boom"

            def _generate(
                self, messages: list[BaseMessage], **kwargs: object
            ) -> ChatResult:
                raise RuntimeError("offline")

            async def _agenerate(
                self, messages: list[BaseMessage], **kwargs: object
            ) -> ChatResult:
                raise RuntimeError("offline")

        findings = asyncio.run(
            run_llm_garbled(
                _chapter("x"), [], _Boom(), GhostCopyeditorConfig()
            )
        )
        assert findings == []

    def test_pipeline_merges_llm_after_deterministic(self) -> None:
        chapter = _chapter("He  walked.\nBroken the.\n")
        llm = JsonStubChatModel(
            payload=json.dumps(
                [
                    {
                        "excerpt": "Broken the.",
                        "message": "Garbled.",
                        "suggestion": "Broken then.",
                        "severity": "warning",
                    }
                ]
            )
        )
        findings = asyncio.run(
            run_chapter_pipeline(
                chapter,
                cfg=GhostCopyeditorConfig(),
                llm=llm,
                llm_enabled=True,
            )
        )
        engines = {f.engine for f in findings}
        assert Engine.DETERMINISTIC in engines
        assert Engine.LLM in engines
        assert any(f.id.startswith("llm-c001-") for f in findings)
        llm_hits = [f for f in findings if f.engine == Engine.LLM]
        assert llm_hits[0].suggestion == "Broken then."
        assert llm_hits[0].applyable is False
        assert llm_hits[0].replacement is None


class TestApplySkipsLlm:
    def test_llm_suggestion_not_written(self) -> None:
        chapter_text = "Broken sentence the.\n"
        chapter = _chapter(chapter_text)
        llm = JsonStubChatModel(
            payload=json.dumps(
                [
                    {
                        "excerpt": "Broken sentence the.",
                        "message": "Garbled.",
                        "suggestion": "The sentence was broken.",
                        "severity": "warning",
                    }
                ]
            )
        )
        findings = asyncio.run(
            run_chapter_pipeline(
                chapter,
                cfg=GhostCopyeditorConfig(),
                llm=llm,
                llm_enabled=True,
            )
        )
        llm_findings = [f for f in findings if f.engine == Engine.LLM]
        assert llm_findings
        for finding in llm_findings:
            assert not is_apply_candidate(finding)
        new_text, applied, _ = apply_to_content(chapter_text, findings)
        assert applied == sum(
            1
            for f in findings
            if f.engine == Engine.DETERMINISTIC and f.metadata.get("applied")
        )
        assert "Broken sentence the." in new_text or "Broken sentence the." in chapter_text
        assert all(not f.metadata.get("applied") for f in llm_findings)


class TestCliLlmFlags:
    def test_no_llm_skips_even_with_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        chapter = tmp_path / "chapter-001.md"
        chapter.write_text("# One\n\nHe walked.\n", encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "companion",
                str(chapter),
                "--model",
                "stub",
                "--no-llm",
                "--no-typesafe",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["llm_enabled"] is False

    def test_model_stub_enables_llm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        chapter = tmp_path / "chapter-002.md"
        chapter.write_text("# Two\n\nHe walked.\n", encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "companion",
                str(chapter),
                "--model",
                "stub",
                "--no-typesafe",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["llm_enabled"] is True
        assert all(
            f["engine"] != "llm" or f["applyable"] is False for f in data["findings"]
        )

    def test_missing_key_non_stub_exits_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setattr(
            "ghostcopyeditor.paths.find_secrets_env", lambda start=None: None
        )
        chapter = tmp_path / "chapter-003.md"
        chapter.write_text("# Three\n\nHe walked.\n", encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "companion",
                str(chapter),
                "--model",
                "gemini-3.8-flash",
                "--no-typesafe",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 1
        assert "API key" in result.output or "api key" in result.output.lower()

    def test_apply_with_llm_findings_does_not_write_llm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        chapter = tmp_path / "chapter-004.md"
        original = "# Four\n\nBroken sentence the.\n"
        chapter.write_text(original, encoding="utf-8")

        payload = json.dumps(
            [
                {
                    "excerpt": "Broken sentence the.",
                    "message": "Garbled.",
                    "suggestion": "REWRITTEN BY LLM",
                    "severity": "warning",
                }
            ]
        )
        stub = JsonStubChatModel(payload=payload)
        monkeypatch.setattr(
            "ghostcopyeditor.commands.companion.get_llm",
            lambda *a, **k: stub,
        )

        result = runner.invoke(
            app,
            [
                "companion",
                str(chapter),
                "--model",
                "stub",
                "--apply",
                "--no-typesafe",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["llm_enabled"] is True
        written = chapter.read_text(encoding="utf-8")
        assert "REWRITTEN BY LLM" not in written
        llm_findings = [f for f in data["findings"] if f["engine"] == "llm"]
        assert llm_findings
        assert all(f["applyable"] is False for f in llm_findings)
