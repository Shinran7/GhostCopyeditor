"""Book lexicon from Autonomicon's worldbuilding glossary.

Each story keeps coined words and special spellings at
``stories/{slug}/canon/style/worldbuilding-glossary.json``.
Those surface forms are intentional. Copy edit must not "correct" them.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from ghostcopyeditor.models.finding import Finding

logger = logging.getLogger(__name__)

_GLOSSARY_REL = Path("canon") / "style" / "worldbuilding-glossary.json"
_MAX_WALK = 8
_PROMPT_TERMS = 80
_DEF_CHARS = 140


@dataclass(frozen=True)
class LexiconEntry:
    """One glossary row: the term, its aliases, and a short definition."""

    term: str
    definition: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class Lexicon:
    """Protected spellings for one book. Empty when no glossary is present."""

    entries: tuple[LexiconEntry, ...] = ()
    source: Path | None = None

    @property
    def forms(self) -> tuple[str, ...]:
        seen: list[str] = []
        folded: set[str] = set()
        for entry in self.entries:
            for raw in (entry.term, *entry.aliases):
                text = raw.strip()
                key = text.casefold()
                if text and key not in folded:
                    folded.add(key)
                    seen.append(text)
        return tuple(seen)

    def protects_word(self, word: str) -> bool:
        """True when *word* is a glossary term or a word inside one."""
        key = word.strip().casefold()
        if not key:
            return False
        if self.is_protected(key):
            return True
        for form in self.forms:
            parts = re.findall(r"[A-Za-z']+", form)
            if any(part.casefold() == key for part in parts):
                return True
        return False

    def is_protected(self, text: str) -> bool:
        """True when *text* is exactly a term or alias."""
        key = " ".join(text.strip().casefold().split())
        if not key:
            return False
        return any(" ".join(form.casefold().split()) == key for form in self.forms)

    def rewrites_protected(self, excerpt: str, suggestion: str) -> bool:
        """True when a suggestion drops a book spelling that the excerpt used."""
        if not excerpt or not suggestion:
            return False
        for form in self.forms:
            if _appears(excerpt, form) and not _appears(suggestion, form):
                return True
        return False

    def prompt_lines(self, limit: int = _PROMPT_TERMS) -> list[str]:
        """Short lines for model context. Terms first, then a clipped definition."""
        lines: list[str] = []
        for entry in self.entries[:limit]:
            label = entry.term.strip()
            if entry.aliases:
                label += " (also " + ", ".join(entry.aliases) + ")"
            definition = " ".join(entry.definition.split())
            if len(definition) > _DEF_CHARS:
                definition = definition[: _DEF_CHARS - 1].rstrip() + "…"
            if definition:
                lines.append(f"- {label}: {definition}")
            else:
                lines.append(f"- {label}")
        return lines


def find_glossary(start: Path) -> Path | None:
    """Find ``canon/style/worldbuilding-glossary.json`` above *start*.

    A chapter at ``stories/{slug}/chapters/chapter-001.md`` resolves to
    ``stories/{slug}/canon/style/worldbuilding-glossary.json``.
    A checkpoint copy wins when the chapter lives under that checkpoint.
    """
    current = start.resolve()
    if current.is_file():
        current = current.parent
    steps = 0
    while steps <= _MAX_WALK:
        candidate = current / _GLOSSARY_REL
        if candidate.is_file():
            return candidate
        if current.parent == current:
            break
        current = current.parent
        steps += 1
    return None


def load_lexicon(start: Path) -> Lexicon:
    """Load the glossary above *start*. Missing or unreadable files yield empty."""
    path = find_glossary(start)
    if path is None:
        return Lexicon()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read worldbuilding glossary at %s", path)
        return Lexicon(source=path)
    if not isinstance(raw, list):
        logger.warning("Worldbuilding glossary is not a list: %s", path)
        return Lexicon(source=path)
    entries: list[LexiconEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        if not term:
            continue
        aliases_raw = item.get("aliases") or []
        aliases: list[str] = []
        if isinstance(aliases_raw, list):
            aliases = [str(alias).strip() for alias in aliases_raw if str(alias).strip()]
        definition = str(item.get("definition") or "").strip()
        entries.append(
            LexiconEntry(term=term, definition=definition, aliases=tuple(aliases))
        )
    return Lexicon(entries=tuple(entries), source=path)


def lexicon_notice(lexicon: Lexicon, story_dir: Path) -> str | None:
    """One operator line when a story tree has or lacks its glossary."""
    if lexicon.entries:
        return f"Book lexicon: {len(lexicon.entries)} terms."
    expected = (story_dir / _GLOSSARY_REL).is_file() or (story_dir / "canon").is_dir()
    in_stories = story_dir.parent.name.lower() == "stories"
    if expected or in_stories:
        return "No worldbuilding glossary found for this story."
    return None


def drop_lexicon_conflicts(findings: list[Finding], lexicon: Lexicon) -> list[Finding]:
    """Remove findings that treat a book spelling as a mistake."""
    if not lexicon.forms:
        return findings
    kept: list[Finding] = []
    for finding in findings:
        excerpt = (finding.location.excerpt or "").strip()
        if lexicon.is_protected(excerpt):
            continue
        echo_word = str(finding.metadata.get("word") or "")
        if finding.rule_id == "echo.local_repeat" and lexicon.protects_word(echo_word):
            continue
        suggestion = (finding.suggestion or finding.replacement or "").strip()
        if lexicon.rewrites_protected(excerpt, suggestion):
            continue
        kept.append(finding)
    return kept


def _appears(text: str, form: str) -> bool:
    pattern = r"(?<!\w)" + re.escape(form) + r"(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


__all__ = [
    "Lexicon",
    "LexiconEntry",
    "drop_lexicon_conflicts",
    "find_glossary",
    "lexicon_notice",
    "load_lexicon",
]
