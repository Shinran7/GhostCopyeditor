"""Configuration model for GhostCopyeditor.

Resolution order:
    1. config.yaml at the project root (found by walking up from CWD
       or the manuscript path)
    2. CLI flags (applied by callers after loading)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from ghostcopyeditor.paths import config_path as _find_config_path


class GhostCopyeditorConfig(BaseModel):
    """GhostCopyeditor configuration."""

    model: str | None = "gemini-3.8-flash"
    temperature: float | None = 0.2
    max_tokens: int | None = None
    format: Literal["terminal", "json"] = "terminal"
    typesafe_enabled: bool = False
    typesafe_confidence_floor: float = 0.55
    typesafe_noul_positive_threshold: float = 0.65
    llm_enabled: bool = False
    apply_default: bool = False
    echo_window_words: int = 40
    echo_min_repeats: int = 3
    wordiness_enabled: bool = True

    @classmethod
    def load(cls, manuscript_path: Path | None = None) -> GhostCopyeditorConfig:
        """Load config from the project-root ``config.yaml``."""
        cfg_path = _find_config_path(manuscript_path)
        if cfg_path is not None and cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()

    def save(self, directory: Path) -> Path:
        """Write config to ``config.yaml`` in *directory*.

        All fields are written so the user can see every available setting.
        Uses a hand-written template so inline comments are preserved.
        """
        path = directory / "config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)

        def _fmt(val: object) -> str:
            if val is None:
                return "null"
            if isinstance(val, bool):
                return str(val).lower()
            return str(val)

        lines = [
            "# LLM model. e.g. gemini-3.8-flash, "
            "accounts/fireworks/models/minimax-m3, gpt-4o, ollama:llama3",
            f"model: {_fmt(self.model)}",
            "",
            "# Temperature for LLM generation. null = provider default",
            f"temperature: {_fmt(self.temperature)}",
            "",
            "# Max tokens for LLM responses. null = provider default",
            f"max_tokens: {_fmt(self.max_tokens)}",
            "",
            "# terminal | json (CLI --format wins)",
            f"format: {_fmt(self.format)}",
            "",
            "# TypeSafe.ai judgments (default off). Needs TYPESAFE_API_KEY.",
            "# Enable after secrets/llm.env, or pass --typesafe.",
            f"typesafe_enabled: {_fmt(self.typesafe_enabled)}",
            "",
            "# Below this Choice confidence, drop the TypeSafe finding.",
            f"typesafe_confidence_floor: {_fmt(self.typesafe_confidence_floor)}",
            "",
            "# Noul at or above this → emit echo/wordiness finding",
            f"typesafe_noul_positive_threshold: {_fmt(self.typesafe_noul_positive_threshold)}",
            "",
            "# LLM garbled/rewrite engine (default off until provider keys exist)",
            f"llm_enabled: {_fmt(self.llm_enabled)}",
            "",
            "# Deterministic apply default (CLI --apply wins when passed)",
            f"apply_default: {_fmt(self.apply_default)}",
            "",
            "# Echo: min repeated content-word hits within window",
            f"echo_window_words: {_fmt(self.echo_window_words)}",
            f"echo_min_repeats: {_fmt(self.echo_min_repeats)}",
            "",
            "# Wordiness: enable built-in phrase map",
            f"wordiness_enabled: {_fmt(self.wordiness_enabled)}",
            "",
        ]

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return path
