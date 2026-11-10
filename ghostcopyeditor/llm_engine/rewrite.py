"""Checked passage rewrites for paragraphs with rhythm, weakener, or hollow notes.

The unit is one or two paragraphs. Two models do the work:

- the **writer** (a model that writes good prose, e.g. the book's own
  writing model) decides what the passage is for and edits it. It may cut,
  merge, and reorder; the edit may be shorter.
- the **checker** compares original and edit for continuity: every fact
  kept, nothing changed, lost, or added. Wording and tone notes are kept
  apart from facts and never reject an edit.

Before the checker runs, GCE's own checks must pass: quoted dialogue word
for word, the same book terms and cast names present, the same paragraph
count, length no more than the band over (and at least a quarter of) the
original, and no new deterministic problem in the passage.

A kept edit becomes one ``rewrite.passage`` finding (``metadata.rewrite_checked``).
It is never applyable: Autonomicon (or the author) decides.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from ghostcopyeditor.canon import CastMember, cast_lines
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.lexicon import Lexicon
from ghostcopyeditor.llm import message_text
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Severity,
    location_from_span,
)

logger = logging.getLogger(__name__)

TARGET_PREFIXES = ("rhythm.shape_run", "rhythm.same_opener_run", "weak.", "hollow.")
CONTEXT_PARAGRAPHS = 3
_MIN_SHARE = 0.25  # an edit may cut down to a quarter of the original words
_CONCURRENCY = 4
_PARA_RE = re.compile(r"[^\n]+(?:\n[^\n]+)*")
_QUOTED_RE = re.compile(r"\"[^\"]*\"|“[^”]*”")
_WORD_RE = re.compile(r"[A-Za-z0-9']+")

WRITER_SYSTEM_PROMPT = """\
You are the line editor on a novel. You get one passage (one or two \
paragraphs) with the text around it, and the copy editor's notes on it.

First decide what the passage is for: what the reader must know, see, or \
feel when it ends. Then edit it so the prose does that job well. The notes \
are hints, not orders; fix the passage, not just the flagged words.

You may cut, merge, split, and reorder sentences. You may cut whole lines \
that do no work: decoration, images that sound literary but mean nothing, \
beats that repeat each other, strings of sentences about what did not \
happen. The edit may be shorter than the original. Do not swap words for \
synonyms to look busy. If the passage already works, change little.

Continuity is the hard rule. This book is written by an automated system \
that reads its own earlier chapters, so every fact a later page might rely \
on must survive: who is present, who does what, objects and their state, \
places, times, numbers, what each character knows or decides, and any \
detail the surrounding text refers back to or sets up. Do not add events, \
objects, or knowledge. Keep names, book terms, pronouns, point of view, and \
tense. Keep quoted dialogue word for word. Keep the paragraph count.

Return ONLY JSON, no fences:
{"purpose": "<one plain sentence>",
 "facts": ["<each fact the passage establishes that must survive>"],
 "cuts": ["<what you cut or changed, and why>"],
 "edit": "<the edited passage>"}
"""

CHECKER_SYSTEM_PROMPT = """\
You check continuity for a novel written by an automated system that reads \
its own earlier chapters. You get an ORIGINAL passage, an EDITED version, \
and the text before and after it.

1. facts: list every fact the ORIGINAL establishes that later text could \
rely on: who is present, who does what, objects and their state, places, \
times, numbers, what characters know or decide, details the surrounding \
text refers to. For each, say whether the EDIT keeps it, changes it, or \
loses it. A fact said in other words is kept.
2. added: facts the EDIT states that the ORIGINAL did not (new events, \
objects, knowledge, sense details). New wording for an old fact is not an \
addition.
3. after_ok: does the AFTER text still read correctly after the EDIT (no \
reference to something the edit removed)?
4. wording: notes on wording, tone, rhythm, or imagery. These are not \
facts; never put them in facts or added.

Return ONLY JSON, no fences:
{"facts": [{"fact": "...", "status": "kept|changed|lost", "note": "..."}],
 "added": ["..."],
 "after_ok": true, "after_note": "...",
 "wording": ["..."]}
"""


@dataclass(frozen=True)
class _Unit:
    """One or two adjacent paragraphs to edit. ``end`` is exclusive."""

    start: int
    end: int
    first: int  # paragraph index
    last: int
    indices: tuple[int, ...]  # target findings inside


def paragraph_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) of each paragraph: runs of non-blank lines."""
    return [m.span() for m in _PARA_RE.finditer(text)]


def _is_prose(paragraph: str) -> bool:
    stripped = paragraph.strip()
    return bool(_WORD_RE.search(stripped)) and not stripped.startswith("#")


def _units(findings: list[Finding], chapter: Chapter, limit: int) -> list[_Unit]:
    """Group target findings by paragraph, merge flagged neighbours in pairs."""
    paras = paragraph_spans(chapter.content)
    hits: dict[int, list[int]] = {}
    for idx, finding in enumerate(findings):
        start = finding.location.char_start
        if start is None or not (finding.rule_id or "").startswith(TARGET_PREFIXES):
            continue
        para = next((i for i, (s, e) in enumerate(paras) if s <= start < e), None)
        if para is not None and _is_prose(chapter.content[slice(*paras[para])]):
            hits.setdefault(para, []).append(idx)
    units: list[_Unit] = []
    pending = sorted(hits)
    while pending:
        first = pending.pop(0)
        last = first
        if pending and pending[0] == first + 1:
            last = pending.pop(0)
        idxs = tuple(hits[first] + (hits[last] if last != first else []))
        units.append(_Unit(paras[first][0], paras[last][1], first, last, idxs))
    # Most-flagged passages first, then back into reading order.
    units.sort(key=lambda u: (-len(u.indices), u.start))
    return sorted(units[:limit], key=lambda u: u.start)


def _context(chapter: Chapter, unit: _Unit) -> tuple[str, str]:
    paras = paragraph_spans(chapter.content)
    text = chapter.content
    lo = max(0, unit.first - CONTEXT_PARAGRAPHS)
    before = "\n\n".join(text[s:e] for s, e in paras[lo : unit.first])
    hi = unit.last + 1 + CONTEXT_PARAGRAPHS
    after = "\n\n".join(text[s:e] for s, e in paras[unit.last + 1 : hi])
    return before, after


def _parse_object(raw: str) -> dict[str, Any] | None:
    from ghostcopyeditor.llm_engine.garbled import _strip_fences

    text = _strip_fences(raw)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _strict_cfg(cfg: GhostCopyeditorConfig) -> GhostCopyeditorConfig:
    """Config that reports every weakener hit (no density gate)."""
    return cfg.model_copy(
        update={
            "weak_qualifier_per_1000": -1.0,
            "weak_filter_per_1000": -1.0,
            "weak_tag_adverb_per_1000": -1.0,
            "weak_min_scene_words": 0,
            "rhythm_min_scene_sentences": 10**9,
            "skip_rules": [],
        }
    )


def _rules_in(findings: list[Finding], start: int, end: int) -> set[str]:
    out: set[str] = set()
    for f in findings:
        loc = f.location
        if loc.char_start is None or loc.char_end is None:
            continue
        if loc.char_start < end and start < loc.char_end:
            out.add(f.rule_id or "")
    return out


def _names_present(text: str, names: list[str]) -> set[str]:
    return {
        name.lower()
        for name in names
        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, flags=re.IGNORECASE)
    }


def verify_edit(
    chapter: Chapter,
    unit: _Unit,
    edit: str,
    cfg: GhostCopyeditorConfig,
    protected: list[str],
    before: list[Finding],
) -> str | None:
    """GCE's own checks. None when *edit* passes, else the failed check."""
    from ghostcopyeditor.checkers import run_deterministic_checkers

    text = chapter.content
    original = text[unit.start : unit.end]
    edit = edit.strip()
    old_words = len(_WORD_RE.findall(original))
    new_words = len(_WORD_RE.findall(edit))
    if not new_words:
        return "empty"
    if new_words > (1 + cfg.rewrite_length_band) * old_words or new_words < _MIN_SHARE * old_words:
        return "length"
    if _QUOTED_RE.findall(original) != _QUOTED_RE.findall(edit):
        return "dialogue"
    if len(paragraph_spans(original)) != len(paragraph_spans(edit)):
        return "paragraphs"
    if _names_present(original, protected) != _names_present(edit, protected):
        return "names"
    new_chapter = dataclasses.replace(chapter, content=text[: unit.start] + edit + text[unit.end :])
    after = run_deterministic_checkers(new_chapter, _strict_cfg(cfg))
    new_rules = _rules_in(after, unit.start, unit.start + len(edit))
    if new_rules - _rules_in(before, unit.start, unit.end):
        return "new_problem"
    return None


def judge_continuity(report: dict[str, Any] | None) -> tuple[list[str], dict[str, Any]]:
    """Reasons to reject from a checker report, plus its cleaned fields."""
    if report is None:
        return ["checker_unreadable"], {}
    facts = [
        {
            "fact": str(f.get("fact") or "").strip(),
            "status": str(f.get("status") or "").strip().lower(),
            "note": str(f.get("note") or "").strip(),
        }
        for f in report.get("facts") or []
        if isinstance(f, dict)
    ]
    added = _str_list(report.get("added"))
    after_ok = report.get("after_ok") is not False
    reasons = [
        f"fact {f['status'] or 'unclear'}: {f['fact']}" for f in facts if f["status"] != "kept"
    ]
    reasons += [f"fact added: {a}" for a in added]
    if not after_ok:
        reasons.append(f"after text breaks: {str(report.get('after_note') or '').strip()}")
    if not facts:
        reasons.append("checker listed no facts")
    clean = {"facts": facts, "added": added, "wording": _str_list(report.get("wording"))}
    return reasons, clean


def _writer_prompt(
    chapter: Chapter,
    unit: _Unit,
    notes: list[str],
    lexicon: Lexicon,
    cast: tuple[CastMember, ...],
) -> str:
    before, after = _context(chapter, unit)
    parts: list[str] = []
    names = cast_lines(cast)
    if names:
        parts.append("CAST (keep names and pronouns):\n" + "\n".join(names))
    lex = lexicon.prompt_lines()
    if lex:
        parts.append("BOOK TERMS (keep exactly):\n" + "\n".join(lex))
    parts.append(f"BEFORE:\n{before}")
    parts.append(f"PASSAGE:\n{chapter.content[unit.start : unit.end]}")
    parts.append(f"AFTER:\n{after}")
    parts.append("NOTES:\n" + "\n".join(f"- {n}" for n in notes))
    return "\n\n".join(parts)


def _checker_prompt(chapter: Chapter, unit: _Unit, edit: str) -> str:
    before, after = _context(chapter, unit)
    return (
        f"BEFORE:\n{before}\n\nORIGINAL:\n{chapter.content[unit.start : unit.end]}"
        f"\n\nEDITED:\n{edit}\n\nAFTER:\n{after}"
    )


async def _ask(llm: Any, system: str, user: str) -> dict[str, Any] | None:
    from langchain_core.messages import HumanMessage, SystemMessage

    response = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
    return _parse_object(message_text(getattr(response, "content", response)))


async def _edit_unit(
    chapter: Chapter,
    unit: _Unit,
    findings: list[Finding],
    writer: Any,
    checker: Any,
    cfg: GhostCopyeditorConfig,
    lexicon: Lexicon,
    cast: tuple[CastMember, ...],
    protected: list[str],
    before: list[Finding],
) -> Finding | list[str]:
    """The passage finding, or the reasons the edit was rejected."""
    notes = [findings[i].message for i in unit.indices]
    try:
        prompt = _writer_prompt(chapter, unit, notes, lexicon, cast)
        draft = await _ask(writer, WRITER_SYSTEM_PROMPT, prompt)
    except Exception:  # noqa: BLE001
        logger.exception("Rewrite writer failed for chapter %s", chapter.chapter_number)
        return ["writer_failed"]
    edit = str((draft or {}).get("edit") or "").strip()
    if not draft or not edit:
        return ["writer_unreadable"]
    original = chapter.content[unit.start : unit.end]
    if " ".join(edit.split()) == " ".join(original.split()):
        return ["unchanged"]
    reason = verify_edit(chapter, unit, edit, cfg, protected, before)
    if reason:
        return [reason]
    try:
        report = await _ask(checker, CHECKER_SYSTEM_PROMPT, _checker_prompt(chapter, unit, edit))
    except Exception:  # noqa: BLE001
        logger.exception("Rewrite checker failed for chapter %s", chapter.chapter_number)
        return ["checker_failed"]
    reasons, checked = judge_continuity(report)
    if reasons:
        return reasons
    purpose = str(draft.get("purpose") or "").strip()
    return Finding(
        id="",
        category=Category.REWRITE,
        severity=Severity.SUGGESTION,
        message="Passage edit" + (f": {purpose}" if purpose else "."),
        location=location_from_span(chapter, unit.start, unit.end),
        engine=Engine.LLM,
        suggestion=edit,
        rule_id="rewrite.passage",
        applyable=False,
        metadata={
            "rewrite_checked": True,
            "rewrite_start": unit.start,
            "rewrite_end": unit.end,
            "rewrite_original": original,
            "purpose": purpose,
            "cuts": _str_list(draft.get("cuts")),
            "facts": checked["facts"],
            "wording": checked["wording"],
            "notes": notes,
            "target_rules": sorted({findings[i].rule_id or "" for i in unit.indices}),
        },
    )


async def run_passage_rewrites(
    chapter: Chapter,
    findings: list[Finding],
    writer: Any,
    checker: Any,
    cfg: GhostCopyeditorConfig,
    lexicon: Lexicon | None = None,
    cast: tuple[CastMember, ...] = (),
) -> list[Finding]:
    """Add checked passage edits for flagged paragraphs."""
    from ghostcopyeditor.checkers import run_deterministic_checkers

    if not cfg.rewrite_enabled or cfg.rewrite_max_per_chapter <= 0:
        return findings
    units = _units(findings, chapter, cfg.rewrite_max_per_chapter)
    if not units:
        return findings
    book = lexicon or Lexicon()
    protected = [*book.forms, *(m.name for m in cast)]
    before = run_deterministic_checkers(chapter, _strict_cfg(cfg))
    gate = asyncio.Semaphore(_CONCURRENCY)

    async def one(unit: _Unit) -> Finding | list[str]:
        async with gate:
            return await _edit_unit(
                chapter, unit, findings, writer, checker, cfg, book, cast, protected, before
            )

    results = await asyncio.gather(*(one(u) for u in units))
    out = list(findings)
    for unit, result in zip(units, results, strict=True):
        if isinstance(result, Finding):
            out.append(result)
            continue
        for idx in unit.indices:
            out[idx] = dataclasses.replace(
                out[idx], metadata={**out[idx].metadata, "rewrite_rejected": result}
            )
    return out


__all__ = [
    "CHECKER_SYSTEM_PROMPT",
    "WRITER_SYSTEM_PROMPT",
    "judge_continuity",
    "paragraph_spans",
    "run_passage_rewrites",
    "verify_edit",
]
