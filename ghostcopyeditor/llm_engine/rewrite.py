"""Checked rewrites for rhythm and weakener notes.

For each scene with notes, one LLM call asks for up to two rewrites per
flagged span. GCE then checks every candidate with its own deterministic
checks and keeps the first one that passes:

- the original flag is gone,
- no new problem appears in the span,
- the scene's variety score does not drop,
- book terms and cast names are unchanged,
- quoted dialogue is unchanged, word for word,
- paragraph breaks are unchanged,
- length stays within the configured band (default ±40%).

A kept rewrite goes into ``suggestion`` with ``metadata.rewrite_checked``.
It is never applyable: Autonomicon (or the author) decides.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from ghostcopyeditor.canon import CastMember, cast_lines
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.lexicon import Lexicon
from ghostcopyeditor.llm import message_text
from ghostcopyeditor.models.finding import Finding, Severity

logger = logging.getLogger(__name__)

TARGET_PREFIXES = ("rhythm.shape_run", "rhythm.same_opener_run", "weak.")
_QUOTED_RE = re.compile(r"\"[^\"]*\"|“[^”]*”")
_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_PARA_BREAK_RE = re.compile(r"\n[ \t\r]*\n")

REWRITE_SYSTEM_PROMPT = """\
You are a fiction line editor. Each target is a passage from one scene that \
reads monotonous (same sentence shape or opening again and again) or leans \
on weak words (very, just, saw, felt, said quietly).

Rewrite each target so the sentences vary in length, opening, and structure. \
Combine or split sentences where that helps. Keep the meaning, the facts, \
the point of view, and the tense. Keep every name and every book term. Keep \
quoted dialogue exactly as written. Keep paragraph breaks where they are. \
Do not add new events, images, or metaphors. Stay close to the original \
length.

Return ONLY a JSON array, no fences, one object per target:
  {"id": "<target id>", "candidates": ["<rewrite 1>", "<rewrite 2>"]}
Give at most two candidates per target.
"""


@dataclass(frozen=True)
class _Target:
    key: str
    start: int
    end: int
    scene: int
    rule: str
    indices: tuple[int, ...]


def _span_for(finding: Finding, sentences: list[Any]) -> tuple[int, int] | None:
    from ghostcopyeditor.nlp.sentences import sentence_index_at

    loc = finding.location
    if loc.char_start is None or loc.char_end is None:
        return None
    first = sentence_index_at(sentences, loc.char_start)
    last = sentence_index_at(sentences, max(loc.char_end - 1, loc.char_start))
    if first is None or last is None:
        return None
    return sentences[first].start, sentences[last].end


def _targets(
    findings: list[Finding], chapter: Chapter, limit: int
) -> list[_Target]:
    from ghostcopyeditor.checkers.regions import scene_number_at, scene_spans
    from ghostcopyeditor.nlp.sentences import prose_sentences

    sentences = prose_sentences(chapter.content)
    scenes = scene_spans(chapter.content)
    by_span: dict[tuple[int, int], list[int]] = defaultdict(list)
    rules: dict[tuple[int, int], str] = {}
    spans: list[tuple[tuple[int, int], int, str]] = []
    for idx, finding in enumerate(findings):
        rule = finding.rule_id or ""
        if not rule.startswith(TARGET_PREFIXES):
            continue
        span = _span_for(finding, sentences)
        if span is not None:
            spans.append((span, idx, rule))
    # Widest spans first, so a narrower note inside one joins it.
    spans.sort(key=lambda row: (row[0][0] - row[0][1], row[0][0]))
    for span, idx, rule in spans:
        # A span inside an already-claimed span joins it.
        host = next((s for s in by_span if s[0] <= span[0] and span[1] <= s[1]), None)
        if host is None:
            if any(s[0] < span[1] and span[0] < s[1] for s in by_span):
                continue  # partial overlap: skip rather than rewrite twice
            host = span
            rules[host] = rule
        by_span[host].append(idx)
    out: list[_Target] = []
    for n, (span, idxs) in enumerate(sorted(by_span.items())[:limit], start=1):
        out.append(
            _Target(
                key=f"t{n}",
                start=span[0],
                end=span[1],
                scene=scene_number_at(span[0], scenes) or 1,
                rule=rules[span],
                indices=tuple(idxs),
            )
        )
    return out


def _parse(raw: str) -> dict[str, list[str]]:
    from ghostcopyeditor.llm_engine.garbled import _strip_fences

    text = _strip_fences(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start < 0 or end <= start:
            return {}
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    if not isinstance(data, list):
        return {}
    out: dict[str, list[str]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        cands = item.get("candidates")
        if isinstance(item.get("id"), str) and isinstance(cands, list):
            out[item["id"]] = [c for c in cands if isinstance(c, str) and c.strip()][:2]
    return out


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


def _protected_counts(text: str, names: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in names:
        pattern = r"(?<!\w)" + re.escape(name) + r"(?!\w)"
        counts[name] = len(re.findall(pattern, text, flags=re.IGNORECASE))
    return counts


def _scene_variety(text: str, scene: int) -> int | None:
    from ghostcopyeditor.nlp.sentence_shape import narration_shapes, scene_metrics
    from ghostcopyeditor.nlp.sentences import prose_sentences

    shapes = narration_shapes([s for s in prose_sentences(text) if s.scene == scene])
    value = scene_metrics(shapes)["variety"]
    return value if isinstance(value, int) else None


def verify_candidate(
    chapter: Chapter,
    target: _Target,
    candidate: str,
    cfg: GhostCopyeditorConfig,
    protected: list[str],
    before: list[Finding],
) -> str | None:
    """Return None when *candidate* passes, else the first failed check."""
    from ghostcopyeditor.checkers import run_deterministic_checkers

    text = chapter.content
    original = text[target.start : target.end]
    candidate = candidate.strip()
    old_words = len(_WORD_RE.findall(original))
    new_words = len(_WORD_RE.findall(candidate))
    band = cfg.rewrite_length_band
    if not old_words or abs(new_words - old_words) > band * old_words:
        return "length"
    if _QUOTED_RE.findall(original) != _QUOTED_RE.findall(candidate):
        return "dialogue"
    if len(_PARA_BREAK_RE.findall(original)) != len(_PARA_BREAK_RE.findall(candidate)):
        return "paragraphs"
    if _protected_counts(original, protected) != _protected_counts(candidate, protected):
        return "names"
    new_text = text[: target.start] + candidate + text[target.end :]
    new_end = target.start + len(candidate)
    new_chapter = dataclasses.replace(chapter, content=new_text)
    after = run_deterministic_checkers(new_chapter, _strict_cfg(cfg))
    new_rules = _rules_in(after, target.start, new_end)
    if target.rule in new_rules:
        return "flag_remains"
    old_rules = _rules_in(before, target.start, target.end)
    if new_rules - old_rules:
        return "new_problem"
    old_var = _scene_variety(text, target.scene)
    new_var = _scene_variety(new_text, target.scene)
    if old_var is not None and new_var is not None and new_var < old_var:
        return "variety_drop"
    return None


def _user_prompt(
    chapter: Chapter, scene: int, targets: list[_Target], lexicon: Lexicon,
    cast: tuple[CastMember, ...],
) -> str:
    from ghostcopyeditor.checkers.regions import scene_spans

    spans = scene_spans(chapter.content)
    span = spans[scene - 1] if 0 < scene <= len(spans) else spans[0]
    parts = [f"Scene {scene} of chapter {chapter.chapter_number}, for context:"]
    parts.append(chapter.content[span.start : span.end].strip())
    lex = lexicon.prompt_lines()
    if lex:
        parts.append("Book terms (keep exactly):\n" + "\n".join(lex))
    names = cast_lines(cast)
    if names:
        parts.append("Cast (keep names and pronouns):\n" + "\n".join(names))
    parts.append("Targets:")
    for t in targets:
        parts.append(json.dumps({"id": t.key, "problem": t.rule,
                                 "text": chapter.content[t.start : t.end]}))
    return "\n\n".join(parts)


async def run_checked_rewrites(
    chapter: Chapter,
    findings: list[Finding],
    llm: Any,
    cfg: GhostCopyeditorConfig,
    lexicon: Lexicon | None = None,
    cast: tuple[CastMember, ...] = (),
) -> list[Finding]:
    """Attach checked rewrites to rhythm and weakener findings."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from ghostcopyeditor.checkers import run_deterministic_checkers

    if not cfg.rewrite_enabled or cfg.rewrite_max_per_chapter <= 0:
        return findings
    targets = _targets(findings, chapter, cfg.rewrite_max_per_chapter)
    if not targets:
        return findings
    book = lexicon or Lexicon()
    protected = [*book.forms, *(m.name for m in cast)]
    before = run_deterministic_checkers(chapter, _strict_cfg(cfg))
    by_scene: dict[int, list[_Target]] = defaultdict(list)
    for t in targets:
        by_scene[t.scene].append(t)
    out = list(findings)
    for scene, scene_targets in sorted(by_scene.items()):
        messages = [
            SystemMessage(content=REWRITE_SYSTEM_PROMPT),
            HumanMessage(content=_user_prompt(chapter, scene, scene_targets, book, cast)),
        ]
        try:
            response = await llm.ainvoke(messages)
        except Exception:  # noqa: BLE001
            logger.exception("Rewrite call failed for chapter %s scene %s",
                             chapter.chapter_number, scene)
            continue
        candidates = _parse(message_text(getattr(response, "content", response)))
        for t in scene_targets:
            reasons: list[str] = []
            for cand in candidates.get(t.key, []):
                reason = verify_candidate(chapter, t, cand, cfg, protected, before)
                if reason is None:
                    for idx in t.indices:
                        f = out[idx]
                        out[idx] = dataclasses.replace(
                            f,
                            severity=Severity.SUGGESTION,
                            suggestion=cand.strip(),
                            metadata={
                                **f.metadata,
                                "rewrite_checked": True,
                                "rewrite_start": t.start,
                                "rewrite_end": t.end,
                                "rewrite_original": chapter.content[t.start : t.end],
                            },
                        )
                    break
                reasons.append(reason)
            else:
                if reasons:
                    for idx in t.indices:
                        out[idx].metadata["rewrite_rejected"] = reasons
    return out


__all__ = ["REWRITE_SYSTEM_PROMPT", "run_checked_rewrites", "verify_candidate"]
