"""Run TypeSafe copy-edit judgments for one chapter."""

from __future__ import annotations

from typing import Any

from ghostcopyeditor.canon import CastMember, cast_lines as format_cast
from ghostcopyeditor.config import GhostCopyeditorConfig
from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.lexicon import Lexicon
from ghostcopyeditor.models.finding import Finding
from ghostcopyeditor.typesafe.adapters import response_to_findings
from ghostcopyeditor.typesafe.client import ask
from ghostcopyeditor.typesafe.questions import copy_edit_questions
from ghostcopyeditor.typesafe.state import build_typesafe_state


async def run_typesafe_judgments(
    chapter: Chapter,
    det_findings: list[Finding],
    typesafe_client: Any,
    cfg: GhostCopyeditorConfig,
    lexicon: Lexicon | None = None,
    cast: tuple[CastMember, ...] = (),
) -> list[Finding]:
    """Ask System One and adapt answers into Finding records."""
    book = lexicon or Lexicon()
    state = build_typesafe_state(
        chapter,
        det_findings,
        lexicon_lines=book.prompt_lines(),
        cast_lines=format_cast(cast),
    )
    candidate_spans = list(state.pop("_candidate_spans", []) or [])
    response = await ask(
        typesafe_client,
        state=state,
        questions=copy_edit_questions(),
    )
    return response_to_findings(
        response,
        chapter,
        confidence_floor=cfg.typesafe_confidence_floor,
        positive_threshold=cfg.typesafe_noul_positive_threshold,
        candidate_spans=candidate_spans,
    )
