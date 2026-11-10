"""LLM judge for hollow-imagery candidates (notes only, never applyable).

``nlp.hollow.hollow_candidates`` finds sentences with a suspect shape. One
call per chapter sends the chapter for context plus the numbered
candidates; the judge marks each HOLLOW or WORKS and names the hollow words.
Only HOLLOW lines become findings (``hollow.image``).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.llm import message_text
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Severity,
    location_from_span,
)

logger = logging.getLogger(__name__)

HOLLOW_SYSTEM_PROMPT = """\
You are a fiction editor reviewing a novel draft written by an LLM. LLM \
prose reaches for lines that sound literary but give the reader nothing: \
"a quiet with no edges", "nobody answered the creak", "a nod rather than a \
promise", "the kitchen's idea of breakfast", objects that wait, want, or \
consider for no reason, abstract nouns doing physical things, tags that \
restate what the sentence already said.

You get the chapter for context, then numbered candidate sentences. Mark a \
candidate HOLLOW when its figure or tag carries no meaning a reader can \
use. Mark it WORKS when the figure adds something concrete (a sense \
detail, a fact, a sharp comparison), when the words are literal in this \
story (a machine that really speaks, a ship that really waits), or when \
there is no figure at all.

Return ONLY a JSON array, no fences:
[{"n": <number>, "label": "HOLLOW|WORKS", "phrase": "<the hollow words, \
copied exactly; empty for WORKS>", "why": "<a few plain words>"}]
"""


def build_hollow_user_prompt(chapter: Chapter, lines: list[str]) -> str:
    numbered = "\n".join(f"{i}. {' '.join(line.split())}" for i, line in enumerate(lines, 1))
    return f"CHAPTER:\n{chapter.content.strip()}\n\nCANDIDATES:\n{numbered}"


def parse_hollow_response(raw: str) -> dict[int, dict[str, str]]:
    """Map candidate number → {label, phrase, why}. Empty on bad JSON."""
    from ghostcopyeditor.llm_engine.garbled import _strip_fences

    text = _strip_fences(raw)
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    out: dict[int, dict[str, str]] = {}
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("n"), int):
            continue
        out[item["n"]] = {
            "label": str(item.get("label") or "").strip().upper(),
            "phrase": str(item.get("phrase") or "").strip(),
            "why": str(item.get("why") or "").strip(),
        }
    return out


def _phrase_span(sentence: str, phrase: str) -> tuple[int, int] | None:
    """Offsets of *phrase* in *sentence*, matching across line wraps."""
    import re

    words = phrase.split()
    if not words:
        return None
    pattern = r"\s+".join(re.escape(w) for w in words)
    match = re.search(pattern, sentence)
    return match.span() if match else None


async def run_hollow_judge(
    chapter: Chapter, llm: Any, cfg: GhostCopyeditorConfig
) -> list[Finding]:
    """Judge this chapter's hollow-imagery candidates; return HOLLOW notes."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from ghostcopyeditor.nlp.hollow import hollow_candidates

    if not cfg.hollow_enabled or cfg.hollow_max_candidates <= 0:
        return []
    candidates = hollow_candidates(chapter.content)[: cfg.hollow_max_candidates]
    if not candidates:
        return []
    messages = [
        SystemMessage(content=HOLLOW_SYSTEM_PROMPT),
        HumanMessage(content=build_hollow_user_prompt(chapter, [c.text for c in candidates])),
    ]
    try:
        response = await llm.ainvoke(messages)
    except Exception:  # noqa: BLE001
        logger.exception("Hollow judge failed for chapter %s", chapter.chapter_number)
        return []
    verdicts = parse_hollow_response(message_text(getattr(response, "content", response)))
    findings: list[Finding] = []
    for n, cand in enumerate(candidates, 1):
        verdict = verdicts.get(n)
        if not verdict or verdict["label"] != "HOLLOW":
            continue
        span = _phrase_span(cand.text, verdict["phrase"])
        start, end = cand.start, cand.end
        if span:
            start, end = cand.start + span[0], cand.start + span[1]
        phrase = chapter.content[start:end]
        why = f" {verdict['why'].rstrip('.')}." if verdict["why"] else ""
        findings.append(
            Finding(
                id="",
                category=Category.HOLLOW,
                severity=Severity.SUGGESTION,
                message=f"Hollow image “{' '.join(phrase.split()).rstrip('.;')}”.{why}",
                location=location_from_span(chapter, start, end),
                engine=Engine.LLM,
                suggestion="(cut it, or say the plain thing it stands for)",
                rule_id="hollow.image",
                applyable=False,
                metadata={
                    "pattern": cand.pattern,
                    "sentence": cand.text,
                    "sentence_start": cand.start,
                    "sentence_end": cand.end,
                },
            )
        )
    return findings


__all__ = [
    "HOLLOW_SYSTEM_PROMPT",
    "build_hollow_user_prompt",
    "parse_hollow_response",
    "run_hollow_judge",
]
