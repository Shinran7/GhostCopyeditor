"""Build capped TypeSafe state and sample candidate passages."""

from __future__ import annotations

import re
from typing import Any

from ghostcopyeditor.checkers.regions import non_prose_spans, span_overlaps_any
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import Category, Finding

PROSE_MAX_CHARS = 12_000
CANDIDATE_MAX_CHARS = 600
CANDIDATE_MAX_COUNT = 8
CANDIDATE_MIN_FOR_LIST = 3

_TERMINAL_RE = re.compile(r"[.?!][\"')\]]*$")
_AGREEMENT_RE = re.compile(
    r"\b(?:they\s+was|he\s+were|she\s+were|it\s+were|i\s+is|we\s+is|"
    r"you\s+is|he\s+don't|she\s+don't|it\s+don't)\b",
    re.IGNORECASE,
)
_PARAGRAPH_RE = re.compile(r"\n\s*\n")


def truncate_middle(text: str, max_chars: int = PROSE_MAX_CHARS) -> str:
    """Keep head and tail; insert an ellipsis marker in the middle when truncated."""
    if len(text) <= max_chars:
        return text
    marker = "\n…\n"
    budget = max_chars - len(marker)
    if budget <= 0:
        return text[:max_chars]
    left = budget // 2
    right = budget - left
    return text[:left] + marker + text[-right:]


def _paragraph_spans(content: str) -> list[tuple[int, int, str]]:
    """Return (start, end, text) for non-empty paragraphs."""
    spans: list[tuple[int, int, str]] = []
    start = 0
    for match in _PARAGRAPH_RE.finditer(content):
        end = match.start()
        chunk = content[start:end]
        if chunk.strip():
            spans.append((start, end, chunk))
        start = match.end()
    if start < len(content):
        chunk = content[start:]
        if chunk.strip():
            spans.append((start, len(content), chunk))
    return spans


def _clip_excerpt(text: str, max_chars: int = CANDIDATE_MAX_CHARS) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _looks_like_fragment(paragraph: str) -> bool:
    stripped = paragraph.strip()
    if len(stripped) <= 40:
        return False
    return _TERMINAL_RE.search(stripped) is None


def sample_candidate_passages(
    chapter: Chapter,
    det_findings: list[Finding],
) -> list[dict[str, Any]]:
    """Prefer up to 8 passages (≤600 chars) from fragments and echo/wordiness hits."""
    content = chapter.content
    skipped = non_prose_spans(content)
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()

    def _add(start: int, end: int, source: str) -> None:
        if start < 0 or end <= start:
            return
        if span_overlaps_any(start, end, skipped):
            return
        key = (start, end)
        if key in seen:
            return
        excerpt = _clip_excerpt(content[start:end])
        if not excerpt:
            return
        seen.add(key)
        candidates.append(
            {
                "text": excerpt,
                "char_start": start,
                "char_end": end,
                "source": source,
            }
        )

    for start, end, para in _paragraph_spans(content):
        if _looks_like_fragment(para) or _AGREEMENT_RE.search(para):
            _add(start, end, "heuristic")
            if len(candidates) >= CANDIDATE_MAX_COUNT:
                break

    echo_wordy = [
        f
        for f in det_findings
        if f.category in (Category.ECHO, Category.WORDINESS)
        and f.location.excerpt
    ]
    # Prefer higher-severity / earlier findings; already in checker order.
    for finding in echo_wordy:
        if len(candidates) >= CANDIDATE_MAX_COUNT:
            break
        loc = finding.location
        if loc.char_start is not None and loc.char_end is not None:
            _add(loc.char_start, loc.char_end, finding.category.value)
        else:
            excerpt = _clip_excerpt(loc.excerpt)
            idx = content.find(excerpt.rstrip("…")) if excerpt else -1
            if idx >= 0:
                _add(idx, idx + len(excerpt.rstrip("…")), finding.category.value)

    return candidates[:CANDIDATE_MAX_COUNT]


def _kept_ranges(content_len: int, max_chars: int) -> list[tuple[int, int]]:
    """Code-point ranges retained by ``truncate_middle``."""
    if content_len <= max_chars:
        return [(0, content_len)]
    marker = "\n…\n"
    budget = max_chars - len(marker)
    if budget <= 0:
        return [(0, max_chars)]
    left = budget // 2
    right = budget - left
    return [(0, left), (content_len - right, content_len)]


def _span_only_in_middle(
    start: int, end: int, kept: list[tuple[int, int]]
) -> bool:
    """True when the span does not overlap any kept head/tail range."""
    for k_start, k_end in kept:
        if start < k_end and end > k_start:
            return False
    return True


def filter_candidates_for_truncate(
    candidates: list[dict[str, Any]],
    content_len: int,
    max_chars: int = PROSE_MAX_CHARS,
) -> list[dict[str, Any]]:
    """Drop candidates that fall only in the discarded middle after truncate."""
    kept = _kept_ranges(content_len, max_chars)
    out: list[dict[str, Any]] = []
    for cand in candidates:
        start = int(cand.get("char_start", -1))
        end = int(cand.get("char_end", -1))
        if start < 0 or end <= start:
            continue
        if _span_only_in_middle(start, end, kept):
            continue
        out.append(cand)
    return out


def build_typesafe_state(
    chapter: Chapter,
    det_findings: list[Finding],
    *,
    max_chars: int = PROSE_MAX_CHARS,
) -> dict[str, Any]:
    """Build the capped System One state for one chapter."""
    candidates = sample_candidate_passages(chapter, det_findings)
    candidates = filter_candidates_for_truncate(
        candidates, len(chapter.content), max_chars=max_chars
    )
    if len(candidates) < CANDIDATE_MIN_FOR_LIST:
        candidates = []

    prose = truncate_middle(chapter.content, max_chars=max_chars)
    return {
        "chapter_number": chapter.chapter_number,
        "title": chapter.title,
        "prose": prose,
        "deterministic_findings": [
            {
                "rule_id": f.rule_id,
                "category": str(f.category),
                "message": f.message,
                "excerpt": f.location.excerpt,
            }
            for f in det_findings[:40]
        ],
        "candidate_passages": [
            {"text": c["text"], "source": c.get("source", "")} for c in candidates
        ],
        # Internal: offsets for adapters (not required by the API contract).
        "_candidate_spans": candidates,
    }
