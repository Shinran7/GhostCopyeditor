"""LLM garbled / mid-edit wreckage detection (report-only for --apply)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.canon import CastMember, cast_lines
from ghostcopyeditor.lexicon import Lexicon
from ghostcopyeditor.repair import mark_program_replacement
from ghostcopyeditor.llm import message_text
from ghostcopyeditor.llm_engine.prompts import (
    GARBLED_SYSTEM_PROMPT,
    build_garbled_user_prompt,
)
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Location,
    Severity,
    location_from_span,
)

logger = logging.getLogger(__name__)

_SEVERITY_MAP = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "suggestion": Severity.SUGGESTION,
    "info": Severity.INFO,
}

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return _FENCE_RE.sub("", text).strip()


def parse_garbled_response(raw: str) -> list[dict[str, Any]]:
    """Parse model JSON into a list of item dicts. Empty on failure."""
    text = _strip_fences(raw)
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to salvage a leading array if the model added trailing prose.
        start = text.find("[")
        end = text.rfind("]")
        if start < 0 or end <= start:
            logger.warning("LLM garbled response was not valid JSON")
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            logger.warning("LLM garbled response was not valid JSON")
            return []

    if isinstance(data, dict) and "findings" in data:
        data = data["findings"]
    if not isinstance(data, list):
        logger.warning("LLM garbled response was not a JSON list")
        return []
    return [item for item in data if isinstance(item, dict)]


def _anchor_location(chapter: Chapter, excerpt: str) -> tuple[Location, dict[str, Any]]:
    """Locate *excerpt* in chapter content; mark unanchored when not found."""
    needle = (excerpt or "").strip()
    meta: dict[str, Any] = {}
    if needle:
        idx = chapter.content.find(needle)
        if idx >= 0:
            return location_from_span(chapter, idx, idx + len(needle), excerpt=needle), meta
    meta["unanchored"] = True
    return (
        Location(
            chapter_number=chapter.chapter_number,
            chapter_path=str(chapter.source_path),
            excerpt=excerpt or "",
        ),
        meta,
    )


def items_to_findings(
    items: list[dict[str, Any]], chapter: Chapter
) -> list[Finding]:
    """Convert parsed LLM items into garbled findings.

    ``replacement`` and ``applyable`` are set only when the suggestion is
    one unique repair of the excerpt. A paraphrase stays a human note.
    """
    findings: list[Finding] = []
    for item in items:
        excerpt = str(item.get("excerpt") or "").strip()
        message = str(item.get("message") or "").strip()
        suggestion = item.get("suggestion")
        suggestion_text = (
            str(suggestion).strip() if suggestion is not None else None
        ) or None
        severity_raw = str(item.get("severity") or "warning").strip().lower()
        severity = _SEVERITY_MAP.get(severity_raw, Severity.WARNING)
        if not message and not excerpt:
            continue
        if not message:
            message = "Passage appears garbled or broken."
        location, meta = _anchor_location(chapter, excerpt)
        findings.append(
            Finding(
                id="",
                category=Category.GARBLED,
                severity=severity,
                message=message,
                location=location,
                engine=Engine.LLM,
                suggestion=suggestion_text,
                rule_id="llm.garbled",
                applyable=False,
                replacement=None,
                metadata=meta,
            )
        )
        mark_program_replacement(findings[-1], chapter)
    return findings


async def run_llm_garbled(
    chapter: Chapter,
    _prior_findings: list[Finding],
    llm: BaseChatModel,
    _cfg: GhostCopyeditorConfig,
    lexicon: Lexicon | None = None,
    cast: tuple[CastMember, ...] = (),
) -> list[Finding]:
    """Ask the LLM for garbled passages and return report-only findings."""
    book = lexicon or Lexicon()
    messages = [
        SystemMessage(content=GARBLED_SYSTEM_PROMPT),
        HumanMessage(
            content=build_garbled_user_prompt(
                chapter.content,
                chapter_number=chapter.chapter_number,
                lexicon_lines=book.prompt_lines(),
                cast_lines=cast_lines(cast),
            )
        ),
    ]
    try:
        response = await llm.ainvoke(messages)
    except Exception:  # noqa: BLE001
        logger.exception(
            "LLM garbled call failed for chapter %s", chapter.chapter_number
        )
        return []

    raw = message_text(getattr(response, "content", response))
    items = parse_garbled_response(raw)
    return items_to_findings(items, chapter)


__all__ = [
    "items_to_findings",
    "parse_garbled_response",
    "run_llm_garbled",
]
