"""In-process library API for Autonomicon and other callers.

One call checks one chapter's text and returns every finding with its
position, sentence span, scene number, rule id, severity, and confidence.

By default it runs the deterministic checks only: fast, no API keys, and no
network. Pass your own LangChain chat model as ``llm`` and/or a TypeSafe
client as ``typesafe_client`` to run those engines too.

Additive only. ``ghostcopyeditor.nlp.detect_missing_predicates`` stays as is.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ghostcopyeditor import API_VERSION
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import Finding
from ghostcopyeditor.models.report import partition_action_list


@dataclass
class ChapterCheck:
    """Result of :func:`check_chapter`.

    ``findings`` is the action list (things a program may revise).
    ``may_look`` holds notes with no automatic fix (echo, rhythm, weakeners
    without a checked rewrite). ``scenes`` holds per-scene counts.
    """

    findings: list[Finding] = field(default_factory=list)
    may_look: list[Finding] = field(default_factory=list)
    scenes: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    api_version: int = API_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_version": self.api_version,
            "findings": [f.to_dict() for f in self.findings],
            "may_look": [f.to_dict() for f in self.may_look],
            "scenes": list(self.scenes),
            "warnings": list(self.warnings),
        }


async def check_chapter_async(
    text: str,
    *,
    chapter_number: int = 0,
    path: str | Path = "",
    config: GhostCopyeditorConfig | None = None,
    llm: Any | None = None,
    typesafe_client: Any | None = None,
    story_dir: str | Path | None = None,
    skip_rules: tuple[str, ...] | list[str] = (),
    rewrites: bool = False,
    role_llms: Any | None = None,
) -> ChapterCheck:
    """Async form of :func:`check_chapter`."""
    from ghostcopyeditor.canon import load_cast
    from ghostcopyeditor.lexicon import load_lexicon
    from ghostcopyeditor.nlp import missing_predicate_skip_warning
    from ghostcopyeditor.pipeline.positions import scene_profiles
    from ghostcopyeditor.pipeline.runner import run_chapter_pipeline

    base = config or GhostCopyeditorConfig()
    cfg = base.model_copy(
        update={
            "skip_rules": [*base.skip_rules, *skip_rules],
            "rewrite_enabled": rewrites,
        }
    )
    chapter = Chapter(
        title="",
        content=text,
        chapter_number=chapter_number,
        source_path=Path(path),
    )
    lexicon = load_lexicon(Path(story_dir)) if story_dir else None
    cast = load_cast(Path(story_dir)) if story_dir else ()
    findings = await run_chapter_pipeline(
        chapter,
        cfg=cfg,
        llm=llm,
        typesafe_client=typesafe_client,
        typesafe_enabled=typesafe_client is not None,
        llm_enabled=llm is not None,
        lexicon=lexicon,
        cast=cast,
        role_llms=role_llms,
    )
    action, may_look = partition_action_list(findings)
    warnings: list[str] = []
    if w := missing_predicate_skip_warning(cfg):
        warnings.append(w)
    return ChapterCheck(
        findings=action,
        may_look=may_look,
        scenes=scene_profiles(chapter),
        warnings=warnings,
    )


def check_chapter(
    text: str,
    *,
    chapter_number: int = 0,
    path: str | Path = "",
    config: GhostCopyeditorConfig | None = None,
    llm: Any | None = None,
    typesafe_client: Any | None = None,
    story_dir: str | Path | None = None,
    skip_rules: tuple[str, ...] | list[str] = (),
    rewrites: bool = False,
    role_llms: Any | None = None,
) -> ChapterCheck:
    """Check one chapter. Safe to call from sync code or inside a running loop.

    ``skip_rules`` drops findings whose ``rule_id`` starts with any entry, so a
    caller can say which problem types it already handles. ``rewrites=True``
    (with ``llm``) attaches checked rewrites to rhythm and weakener notes.
    """
    coro_args: dict[str, Any] = {
        "chapter_number": chapter_number,
        "path": path,
        "config": config,
        "llm": llm,
        "typesafe_client": typesafe_client,
        "story_dir": story_dir,
        "skip_rules": skip_rules,
        "rewrites": rewrites,
        "role_llms": role_llms,
    }
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(check_chapter_async(text, **coro_args))
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(
            asyncio.run, check_chapter_async(text, **coro_args)
        ).result()


__all__ = ["API_VERSION", "ChapterCheck", "check_chapter", "check_chapter_async"]
