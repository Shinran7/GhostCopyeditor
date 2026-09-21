"""Tests for secrets loading and LLM factory."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ghostcopyeditor.llm import (
    get_llm,
    load_secrets,
    message_text,
    resolve_model_name,
)


class TestLoadSecrets:
    def test_loads_keys_from_env_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "llm.env").write_text(
            "# comment\n"
            "GHOSTCOPYEDITOR_TEST_KEY=from-file\n"
            "EMPTY_KEY=\n"
            "\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GHOSTCOPYEDITOR_TEST_KEY", raising=False)
        monkeypatch.setattr(
            "ghostcopyeditor.paths.find_secrets_env",
            lambda start=None: secrets_dir / "llm.env",
        )

        load_secrets()
        assert os.environ.get("GHOSTCOPYEDITOR_TEST_KEY") == "from-file"
        assert "EMPTY_KEY" not in os.environ

    def test_does_not_overwrite_existing_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secrets_dir = tmp_path / "secrets"
        secrets_dir.mkdir()
        (secrets_dir / "llm.env").write_text(
            "GHOSTCOPYEDITOR_TEST_KEY=from-file\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("GHOSTCOPYEDITOR_TEST_KEY", "already-set")
        monkeypatch.setattr(
            "ghostcopyeditor.paths.find_secrets_env",
            lambda start=None: secrets_dir / "llm.env",
        )

        load_secrets()
        assert os.environ["GHOSTCOPYEDITOR_TEST_KEY"] == "already-set"

    def test_noop_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "ghostcopyeditor.paths.find_secrets_env", lambda start=None: None
        )
        load_secrets()  # must not raise


class TestMessageTextExtras:
    def test_part_objects_and_fallback(self) -> None:
        class _Part:
            text = "part"

        assert message_text([_Part()]) == "part"
        assert message_text(42) == "42"


class TestGetLlm:
    def test_stub_model(self) -> None:
        llm = get_llm("stub")
        assert getattr(llm, "_llm_type") == "stub"
        result = llm.invoke("hello")
        assert "stub" in message_text(result.content).lower() or "chars" in message_text(
            result.content
        ).lower()

    def test_resolve_model_prefers_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.yaml").write_text("model: gemini-3.8-flash\n", encoding="utf-8")
        assert resolve_model_name("stub", manuscript_path=tmp_path) == "stub"
        assert resolve_model_name(None, manuscript_path=tmp_path) == "gemini-3.8-flash"

    def test_missing_gemini_key_falls_back_to_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setattr(
            "ghostcopyeditor.paths.find_secrets_env", lambda start=None: None
        )
        llm = get_llm("gemini-3.8-flash")
        assert getattr(llm, "_llm_type") == "stub"

    def test_fireworks_invalid_id_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FIREWORKS_API_KEY", "fw-test")
        llm = get_llm("fireworks:minimax-m3")
        assert getattr(llm, "_llm_type") == "stub"

    def test_fireworks_missing_key_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
        monkeypatch.setattr(
            "ghostcopyeditor.paths.find_secrets_env", lambda start=None: None
        )
        llm = get_llm("accounts/fireworks/models/minimax-m3")
        assert getattr(llm, "_llm_type") == "stub"

    def test_no_model_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import typer

        monkeypatch.setattr(
            "ghostcopyeditor.llm.resolve_model_name",
            lambda model=None, manuscript_path=None: None,
        )
        with pytest.raises(typer.Exit):
            get_llm(None)

    def test_fireworks_reasoning_effort(self) -> None:
        from ghostcopyeditor.llm import _fireworks_reasoning_effort

        assert _fireworks_reasoning_effort("accounts/fireworks/models/minimax-m3") == "none"
        assert _fireworks_reasoning_effort("accounts/fireworks/models/glm-5p3") == "low"
        assert (
            _fireworks_reasoning_effort("accounts/fireworks/models/glm-5.3", "high")
            == "high"
        )

    def test_provider_success_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys
        from types import ModuleType

        monkeypatch.chdir(tmp_path)
        (tmp_path / "config.yaml").write_text(
            "model: stub\ntemperature: 0.2\nmax_tokens: 100\n",
            encoding="utf-8",
        )

        def _install(name: str, attr: str, label: str) -> None:
            mod = ModuleType(name)

            class _Fake:
                def __init__(self, **kwargs: object) -> None:
                    self.kwargs = kwargs
                    self._llm_type = label

            setattr(mod, attr, _Fake)
            monkeypatch.setitem(sys.modules, name, mod)

        _install("langchain_ollama", "ChatOllama", "fake-ollama")
        llm = get_llm("ollama:llama3", manuscript_path=tmp_path)
        assert getattr(llm, "_llm_type") == "fake-ollama"

        monkeypatch.setenv("FIREWORKS_API_KEY", "fw-test")
        _install("langchain_openai", "ChatOpenAI", "fake-fw")
        llm = get_llm(
            "accounts/fireworks/models/minimax-m3", manuscript_path=tmp_path
        )
        assert getattr(llm, "_llm_type") == "fake-fw"

        monkeypatch.setenv("GEMINI_API_KEY", "gem-test")
        _install("langchain_google_genai", "ChatGoogleGenerativeAI", "fake-gem")
        llm = get_llm("gemini-3.8-flash", manuscript_path=tmp_path)
        assert getattr(llm, "_llm_type") == "fake-gem"

        _install("langchain_openai", "ChatOpenAI", "fake-oai")
        llm = get_llm("gpt-4o", manuscript_path=tmp_path)
        assert getattr(llm, "_llm_type") == "fake-oai"

        _install("langchain_anthropic", "ChatAnthropic", "fake-claude")
        llm = get_llm("claude-sonnet-4-20250514", manuscript_path=tmp_path)
        assert getattr(llm, "_llm_type") == "fake-claude"

        _install("langchain_xai", "ChatXAI", "fake-grok")
        llm = get_llm("grok-beta", manuscript_path=tmp_path)
        assert getattr(llm, "_llm_type") == "fake-grok"

    def test_provider_import_failure_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys
        from types import ModuleType

        mod = ModuleType("langchain_openai")

        def _boom(**_kwargs: object) -> object:
            raise RuntimeError("nope")

        mod.ChatOpenAI = _boom  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "langchain_openai", mod)
        llm = get_llm("gpt-4o")
        assert getattr(llm, "_llm_type") == "stub"

        ollama = ModuleType("langchain_ollama")

        def _ollama_boom(**_kwargs: object) -> object:
            raise RuntimeError("nope")

        ollama.ChatOllama = _ollama_boom  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "langchain_ollama", ollama)
        llm = get_llm("ollama:llama3")
        assert getattr(llm, "_llm_type") == "stub"
