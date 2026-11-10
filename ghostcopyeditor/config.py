"""Configuration model for GhostCopyeditor.

Resolution order:
    1. config.yaml at the project root (found by walking up from CWD
       or the manuscript path)
    2. CLI flags (applied by callers after loading)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from ghostcopyeditor.paths import config_path as _find_config_path


class StyleGuide(BaseModel):
    """Per-book style guide (see ``checkers/style_guide.py``)."""

    banned: list[str] = []
    pet_words: dict[str, int] = {}
    spellings: dict[str, str] = {}


class GhostCopyeditorConfig(BaseModel):
    """GhostCopyeditor configuration."""

    model: str | None = "gemini-3.8-flash"
    temperature: float | None = 0.2
    max_tokens: int | None = None
    format: Literal["terminal", "json"] = "terminal"
    typesafe_enabled: bool = True
    typesafe_confidence_floor: float = 0.55
    typesafe_noul_positive_threshold: float = 0.65
    llm_enabled: bool = True
    apply_default: bool = False
    echo_window_words: int = 40
    echo_min_repeats: int = 3
    echo_phrase_min_n: int = 3
    echo_phrase_max_n: int = 4
    echo_phrase_max_gap: int = 2
    wordiness_enabled: bool = True
    missing_predicate_enabled: bool = True
    missing_predicate_min_tokens: int = 5
    missing_predicate_skip_dialogue_heavy: bool = True
    missing_predicate_typesafe_confirm: bool = True
    missing_predicate_require_period: bool = True
    rhythm_enabled: bool = True
    rhythm_opener_run: int = 3
    rhythm_shape_run: int = 4
    rhythm_short_words: int = 14
    rhythm_flat_variety: int = 62
    rhythm_min_scene_sentences: int = 20
    weakeners_enabled: bool = True
    weak_qualifier_per_1000: float = 3.0
    weak_filter_per_1000: float = 3.0
    weak_tag_adverb_per_1000: float = 1.0
    weak_min_scene_words: int = 300
    style_guide: StyleGuide = StyleGuide()
    rewrite_enabled: bool = True
    rewrite_max_per_chapter: int = 8
    rewrite_length_band: float = 0.4
    skip_rules: list[str] = []

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
            if isinstance(val, (list, dict)):
                return json.dumps(val)
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
            "# TypeSafe.ai judgments (on by default). Needs TYPESAFE_API_KEY.",
            "# Pass --no-typesafe to skip.",
            f"typesafe_enabled: {_fmt(self.typesafe_enabled)}",
            "",
            "# Below this Choice confidence, drop the TypeSafe finding.",
            f"typesafe_confidence_floor: {_fmt(self.typesafe_confidence_floor)}",
            "",
            "# Noul at or above this → emit echo/wordiness finding",
            f"typesafe_noul_positive_threshold: {_fmt(self.typesafe_noul_positive_threshold)}",
            "",
            "# LLM garbled/rewrite engine (on by default). Needs a provider key.",
            f"llm_enabled: {_fmt(self.llm_enabled)}",
            "",
            "# Deterministic apply default (CLI --apply wins when passed)",
            f"apply_default: {_fmt(self.apply_default)}",
            "",
            "# Echo: min repeated content-word hits within window",
            f"echo_window_words: {_fmt(self.echo_window_words)}",
            f"echo_min_repeats: {_fmt(self.echo_min_repeats)}",
            "",
            "# Echo: close-proximity phrase stutter (3–4 word n-grams, gap ≤ N)",
            f"echo_phrase_min_n: {_fmt(self.echo_phrase_min_n)}",
            f"echo_phrase_max_n: {_fmt(self.echo_phrase_max_n)}",
            f"echo_phrase_max_gap: {_fmt(self.echo_phrase_max_gap)}",
            "",
            "# Wordiness: enable built-in phrase map",
            f"wordiness_enabled: {_fmt(self.wordiness_enabled)}",
            "",
            "# Missing predicate: spaCy no-finite-verb detect (needs [nlp] extra)",
            f"missing_predicate_enabled: {_fmt(self.missing_predicate_enabled)}",
            f"missing_predicate_min_tokens: {_fmt(self.missing_predicate_min_tokens)}",
            (
                "# Skip dialogue-heavy sentences (ASCII double quotes)"
            ),
            (
                "missing_predicate_skip_dialogue_heavy: "
                f"{_fmt(self.missing_predicate_skip_dialogue_heavy)}"
            ),
            (
                "# TypeSafe per-hit confirm (intentional → INFO)"
            ),
            (
                "missing_predicate_typesafe_confirm: "
                f"{_fmt(self.missing_predicate_typesafe_confirm)}"
            ),
            "# v1: only period-terminated sentences are loud",
            (
                "missing_predicate_require_period: "
                f"{_fmt(self.missing_predicate_require_period)}"
            ),
            "",
            "# Rhythm: syntactic monotony notes (narration only)",
            f"rhythm_enabled: {_fmt(self.rhythm_enabled)}",
            "# Flag N+ sentences in a row with the same first word",
            f"rhythm_opener_run: {_fmt(self.rhythm_opener_run)}",
            "# Flag N+ short subject-then-verb sentences in a row",
            f"rhythm_shape_run: {_fmt(self.rhythm_shape_run)}",
            f"rhythm_short_words: {_fmt(self.rhythm_short_words)}",
            "# Flag a scene whose variety score (0-100) is below this",
            f"rhythm_flat_variety: {_fmt(self.rhythm_flat_variety)}",
            f"rhythm_min_scene_sentences: {_fmt(self.rhythm_min_scene_sentences)}",
            "",
            "# Weakeners: flag only when a scene is over the per-1,000-word limit",
            f"weakeners_enabled: {_fmt(self.weakeners_enabled)}",
            f"weak_qualifier_per_1000: {_fmt(self.weak_qualifier_per_1000)}",
            f"weak_filter_per_1000: {_fmt(self.weak_filter_per_1000)}",
            f"weak_tag_adverb_per_1000: {_fmt(self.weak_tag_adverb_per_1000)}",
            f"weak_min_scene_words: {_fmt(self.weak_min_scene_words)}",
            "",
            "# Style guide: banned phrases, pet words {word: per-chapter limit},",
            "# house spellings {wrong: right}",
            f"style_guide: {_fmt(self.style_guide.model_dump())}",
            "",
            "# Checked rewrites for rhythm/weakener notes (needs the LLM engine)",
            f"rewrite_enabled: {_fmt(self.rewrite_enabled)}",
            f"rewrite_max_per_chapter: {_fmt(self.rewrite_max_per_chapter)}",
            "# Rewrite word count must stay within this share of the original",
            f"rewrite_length_band: {_fmt(self.rewrite_length_band)}",
            "",
            "# Drop findings whose rule id starts with any of these (e.g. echo.)",
            f"skip_rules: {_fmt(self.skip_rules)}",
            "",
        ]

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return path
