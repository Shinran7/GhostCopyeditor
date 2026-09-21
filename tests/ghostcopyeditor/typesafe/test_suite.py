"""Unit tests for TypeSafe helpers (mocked client; no network)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Location,
    Severity,
)
from ghostcopyeditor.pipeline.runner import run_chapter_pipeline
from ghostcopyeditor.typesafe.adapters import response_to_findings
from ghostcopyeditor.typesafe.client import (
    TypesafeConfigError,
    ask,
    ensure_typesafe_api_key,
    ensure_typesafe_sdk,
)
from ghostcopyeditor.typesafe.questions import COPY_EDIT_QUESTIONS, copy_edit_questions
from ghostcopyeditor.typesafe.routing import noul_band, resolve_typesafe_enabled
from ghostcopyeditor.typesafe.state import (
    build_typesafe_state,
    filter_candidates_for_truncate,
    sample_candidate_passages,
    truncate_middle,
)


def _chapter(content: str, number: int = 1) -> Chapter:
    return Chapter(
        title="T",
        content=content,
        chapter_number=number,
        source_path=Path(f"/story/chapters/chapter-{number:03d}.md"),
    )


def _det(
    *,
    category: Category = Category.ECHO,
    excerpt: str = "repeated word",
    start: int | None = 0,
    end: int | None = 13,
    message: str = "echo",
) -> Finding:
    return Finding(
        id="",
        category=category,
        severity=Severity.SUGGESTION,
        message=message,
        location=Location(
            chapter_number=1,
            chapter_path="/x.md",
            char_start=start,
            char_end=end,
            excerpt=excerpt,
        ),
        engine=Engine.DETERMINISTIC,
        rule_id="echo.local_repeat",
    )


class TestResolveToggle:
    def test_cli_true_wins(self) -> None:
        cfg = GhostCopyeditorConfig(typesafe_enabled=False)
        assert resolve_typesafe_enabled(True, cfg) is True

    def test_cli_false_wins(self) -> None:
        cfg = GhostCopyeditorConfig(typesafe_enabled=True)
        assert resolve_typesafe_enabled(False, cfg) is False

    def test_falls_back_to_config(self) -> None:
        cfg = GhostCopyeditorConfig(typesafe_enabled=True)
        assert resolve_typesafe_enabled(None, cfg) is True

    def test_default_off(self) -> None:
        cfg = GhostCopyeditorConfig()
        assert resolve_typesafe_enabled(None, cfg) is False
        assert cfg.typesafe_enabled is False


class TestEnsureKey:
    def test_missing_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        with pytest.raises(TypesafeConfigError, match="TYPESAFE_API_KEY"):
            ensure_typesafe_api_key()

    def test_blank_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TYPESAFE_API_KEY", "   ")
        with pytest.raises(TypesafeConfigError):
            ensure_typesafe_api_key()

    def test_present_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TYPESAFE_API_KEY", "sk-test")
        ensure_typesafe_api_key()


class TestEnsureSdk:
    def test_missing_sdk_raises_actionable_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import builtins

        real_import = builtins.__import__

        def _fake_import(name: str, *args: object, **kwargs: object):  # noqa: ANN001
            if name == "typesafe_sdk" or name.startswith("typesafe_sdk."):
                raise ImportError("No module named 'typesafe_sdk'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)
        monkeypatch.setattr(
            "ghostcopyeditor.paths.package_project_root", lambda: None
        )
        with pytest.raises(TypesafeConfigError, match="typesafe_sdk package") as exc_info:
            ensure_typesafe_sdk()
        msg = str(exc_info.value)
        assert "uv add typesafe-sdk" in msg
        assert "--no-typesafe" in msg

    def test_missing_sdk_mentions_editable_root(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import builtins

        real_import = builtins.__import__

        def _fake_import(name: str, *args: object, **kwargs: object):  # noqa: ANN001
            if name == "typesafe_sdk" or name.startswith("typesafe_sdk."):
                raise ImportError("No module named 'typesafe_sdk'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)
        monkeypatch.setattr(
            "ghostcopyeditor.paths.package_project_root", lambda: tmp_path
        )
        with pytest.raises(TypesafeConfigError) as exc_info:
            ensure_typesafe_sdk()
        assert str(tmp_path) in str(exc_info.value)

    def test_sdk_present_ok(self) -> None:
        ensure_typesafe_sdk()


class TestRouting:
    def test_noul_bands(self) -> None:
        assert noul_band(0.7) == "positive"
        assert noul_band(0.5) == "mid"
        assert noul_band(0.2) == "negative"

    def test_custom_positive_threshold(self) -> None:
        assert noul_band(0.66, positive_threshold=0.7) == "mid"
        assert noul_band(0.7, positive_threshold=0.7) == "positive"


class TestTruncateMiddle:
    def test_short_unchanged(self) -> None:
        assert truncate_middle("hello", max_chars=10) == "hello"

    def test_long_keeps_head_and_tail(self) -> None:
        text = "A" * 50 + "MIDDLE" + "B" * 50
        out = truncate_middle(text, max_chars=40)
        assert out.startswith("A")
        assert out.endswith("B")
        assert "…" in out
        assert len(out) <= 40
        assert "MIDDLE" not in out

    def test_tiny_budget_falls_back_to_prefix(self) -> None:
        assert len(truncate_middle("abcdefghij", max_chars=2)) <= 2


class TestCandidateSampling:
    def test_fragment_paragraph_sampled(self) -> None:
        para = (
            "This long paragraph never ends with terminal punctuation and "
            "keeps going past forty characters on purpose"
        )
        chapter = _chapter(para + "\n\nNext sentence ends here.")
        cands = sample_candidate_passages(chapter, [])
        assert any("never ends" in c["text"] for c in cands)

    def test_echo_finding_becomes_candidate(self) -> None:
        content = "alpha beta gamma repeated word here and more text"
        start = content.index("repeated word")
        end = start + len("repeated word")
        chapter = _chapter(content)
        cands = sample_candidate_passages(
            chapter, [_det(excerpt="repeated word", start=start, end=end)]
        )
        assert any(c["source"] == "echo" for c in cands)

    def test_fewer_than_three_cleared_in_state(self) -> None:
        chapter = _chapter("Short. Another. Done.")
        state = build_typesafe_state(chapter, [])
        assert state["candidate_passages"] == []
        assert state["_candidate_spans"] == []

    def test_middle_only_candidates_dropped(self) -> None:
        content = "H" * 100 + "TARGETSPAN" + "T" * 100
        start = content.index("TARGETSPAN")
        end = start + len("TARGETSPAN")
        filtered = filter_candidates_for_truncate(
            [{"text": "TARGETSPAN", "char_start": start, "char_end": end}],
            len(content),
            max_chars=40,
        )
        assert filtered == []


class TestAdapters:
    def test_grammar_error_emits(self) -> None:
        chapter = _chapter("They was walking down the road carefully.")
        response = SimpleNamespace(
            choices={
                "copy.grammar_ambiguity": SimpleNamespace(
                    choice="error", confidence=0.9
                ),
                "copy.style_consistency": SimpleNamespace(
                    choice="ok", confidence=0.9
                ),
            },
            nouls={},
        )
        findings = response_to_findings(
            response,
            chapter,
            candidate_spans=[
                {
                    "text": "They was walking",
                    "char_start": 0,
                    "char_end": 16,
                    "source": "heuristic",
                }
            ],
        )
        assert len(findings) == 1
        assert findings[0].engine == Engine.TYPESAFE
        assert findings[0].rule_id == "copy.grammar_ambiguity"
        assert findings[0].severity == Severity.ERROR
        assert findings[0].applyable is False
        assert findings[0].confidence == 0.9

    def test_grammar_low_confidence_dropped(self) -> None:
        chapter = _chapter("They was walking.")
        response = SimpleNamespace(
            choices={
                "copy.grammar_ambiguity": SimpleNamespace(
                    choice="error", confidence=0.2
                ),
            },
            nouls={},
        )
        assert response_to_findings(response, chapter, confidence_floor=0.55) == []

    def test_grammar_ok_dropped(self) -> None:
        chapter = _chapter("Fine prose here.")
        response = SimpleNamespace(
            choices={
                "copy.grammar_ambiguity": SimpleNamespace(
                    choice="ok", confidence=0.99
                ),
            },
            nouls={},
        )
        assert response_to_findings(response, chapter) == []

    def test_style_concern_emits(self) -> None:
        chapter = _chapter("The knight doth stride. Then he goes modern.")
        response = SimpleNamespace(
            choices={
                "copy.style_consistency": SimpleNamespace(
                    choice="concern", confidence=0.8
                ),
            },
            nouls={},
        )
        findings = response_to_findings(response, chapter)
        assert len(findings) == 1
        assert findings[0].category == Category.STYLE
        assert findings[0].severity == Severity.WARNING
        assert findings[0].rule_id == "copy.style_consistency"

    def test_noul_positive_emits_echo(self) -> None:
        chapter = _chapter("The dark dark corridor stretched on.")
        response = SimpleNamespace(
            choices={},
            nouls={"copy.echo_context": SimpleNamespace(noul=0.8)},
        )
        findings = response_to_findings(
            response,
            chapter,
            candidate_spans=[
                {
                    "text": "dark dark",
                    "char_start": 4,
                    "char_end": 13,
                    "source": "echo",
                }
            ],
        )
        assert len(findings) == 1
        assert findings[0].category == Category.ECHO
        assert findings[0].confidence == 0.8
        assert findings[0].metadata.get("noul") == 0.8

    def test_noul_mid_and_negative_dropped(self) -> None:
        chapter = _chapter("Plain text without much going on here.")
        response = SimpleNamespace(
            choices={},
            nouls={
                "copy.echo_context": SimpleNamespace(noul=0.5),
                "copy.wordiness_context": SimpleNamespace(noul=0.1),
            },
        )
        assert response_to_findings(response, chapter) == []

    def test_noul_positive_emits_wordiness(self) -> None:
        chapter = _chapter("In order to finish the task he moved slowly.")
        response = SimpleNamespace(
            choices={},
            nouls={"copy.wordiness_context": SimpleNamespace(noul=0.77)},
        )
        findings = response_to_findings(
            response,
            chapter,
            candidate_spans=[
                {
                    "text": "In order to",
                    "char_start": 0,
                    "char_end": 11,
                    "source": "wordiness",
                }
            ],
        )
        assert len(findings) == 1
        assert findings[0].category == Category.WORDINESS
        assert findings[0].rule_id == "copy.wordiness_context"
        assert findings[0].confidence == 0.77

    def test_unanchored_when_excerpt_missing(self) -> None:
        chapter = _chapter("Hello world.")
        response = SimpleNamespace(
            choices={
                "copy.grammar_ambiguity": SimpleNamespace(
                    choice="warning", confidence=0.9
                ),
            },
            nouls={},
        )
        findings = response_to_findings(
            response,
            chapter,
            candidate_spans=[
                {
                    "text": "not-in-chapter",
                    "char_start": None,
                    "char_end": None,
                    "source": "heuristic",
                }
            ],
        )
        assert findings[0].metadata.get("unanchored") is True


class TestQuestionBank:
    def test_keys(self) -> None:
        qs = copy_edit_questions()
        assert set(qs) == set(COPY_EDIT_QUESTIONS)


class TestAskAndPipeline:
    @pytest.mark.asyncio
    async def test_ask_calls_system_one(self) -> None:
        class _Client:
            def __init__(self) -> None:
                self.calls: list[dict[str, Any]] = []

            async def system_one(self, **kwargs: Any) -> SimpleNamespace:
                self.calls.append(kwargs)
                return SimpleNamespace(choices={}, nouls={}, usage={"n": 1}, model="jev")

        client = _Client()
        resp = await ask(client, state={"prose": "x"}, questions={"q": object()})
        assert resp.choices == {}
        assert client.calls[0]["model"] == "jev-latest"

    @pytest.mark.asyncio
    async def test_ask_swallows_usage_logging_errors(self) -> None:
        class _BadUsage:
            @property
            def usage(self) -> None:
                raise RuntimeError("boom")

            model = "jev"

            choices: dict[str, Any] = {}
            nouls: dict[str, Any] = {}

        class _Client:
            async def system_one(self, **_kwargs: Any) -> _BadUsage:
                return _BadUsage()

        resp = await ask(_Client(), state={}, questions={})
        assert resp.model == "jev"

    @pytest.mark.asyncio
    async def test_pipeline_merges_typesafe_findings(self) -> None:
        chapter = _chapter("He  walked into the dark dark hall.")

        class _Client:
            async def system_one(self, **_kwargs: Any) -> SimpleNamespace:
                return SimpleNamespace(
                    choices={
                        "copy.grammar_ambiguity": SimpleNamespace(
                            choice="ok", confidence=0.9
                        ),
                        "copy.style_consistency": SimpleNamespace(
                            choice="ok", confidence=0.9
                        ),
                    },
                    nouls={
                        "copy.echo_context": SimpleNamespace(noul=0.9),
                        "copy.wordiness_context": SimpleNamespace(noul=0.1),
                    },
                )

        findings = await run_chapter_pipeline(
            chapter,
            cfg=GhostCopyeditorConfig(),
            typesafe_client=_Client(),
            typesafe_enabled=True,
        )
        engines = {f.engine for f in findings}
        assert Engine.DETERMINISTIC in engines
        assert Engine.TYPESAFE in engines
        ts = [f for f in findings if f.engine == Engine.TYPESAFE]
        assert all(f.id.startswith("ts-c001-") for f in ts)
        assert all(f.applyable is False for f in ts)

    @pytest.mark.asyncio
    async def test_pipeline_skips_when_disabled(self) -> None:
        chapter = _chapter("He  walked.")

        class _Boom:
            async def system_one(self, **_kwargs: Any) -> None:
                raise AssertionError("should not call TypeSafe when disabled")

        findings = await run_chapter_pipeline(
            chapter,
            cfg=GhostCopyeditorConfig(),
            typesafe_client=_Boom(),
            typesafe_enabled=False,
        )
        assert all(f.engine == Engine.DETERMINISTIC for f in findings)
