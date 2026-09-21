"""Story cast from ``canon/characters/*.json``.

Each file has a name and a pronouns field such as ``he/him``. Copy edit
uses that list to keep names, and to keep a pronoun note only when it
matches the one named person in the sentence.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from ghostcopyeditor.ingestion import Chapter
from ghostcopyeditor.models.finding import (
    Category,
    Engine,
    Finding,
    Location,
    Severity,
)
from ghostcopyeditor.repair import (
    _pronoun_family,
    drop_pronoun_guesses,
    is_pronoun_guess,
)

logger = logging.getLogger(__name__)

_CHARACTERS_REL = Path("canon") / "characters"
_MAX_WALK = 8
_NAME_RE_CACHE: dict[str, re.Pattern[str]] = {}


@dataclass(frozen=True)
class CastMember:
    """One person from the story's character files."""

    name: str
    pronouns: str
    family: int | None
    tokens: tuple[str, ...]
    path: str = ""


def _family_for_label(label: str) -> int | None:
    first = label.split("/", 1)[0].strip()
    if not first:
        return None
    return _pronoun_family(first)


def _unique_tokens(names: list[str]) -> dict[str, tuple[str, ...]]:
    """Full name, plus a first or last name only when nobody else shares it."""
    firsts: dict[str, int] = {}
    lasts: dict[str, int] = {}
    parsed: list[tuple[str, list[str]]] = []
    for name in names:
        parts = [part for part in name.split() if part]
        parsed.append((name, parts))
        if parts:
            firsts[parts[0].casefold()] = firsts.get(parts[0].casefold(), 0) + 1
            if len(parts) > 1:
                lasts[parts[-1].casefold()] = lasts.get(parts[-1].casefold(), 0) + 1
    out: dict[str, tuple[str, ...]] = {}
    for name, parts in parsed:
        tokens = [name]
        # One-letter names match ordinary words. Two letters are kept when unique.
        if (
            parts
            and firsts.get(parts[0].casefold(), 0) == 1
            and len(parts[0]) >= 2
            and parts[0].casefold() not in {"an", "or", "of", "to", "in", "on", "at"}
        ):
            tokens.append(parts[0])
        if (
            len(parts) > 1
            and lasts.get(parts[-1].casefold(), 0) == 1
            and len(parts[-1]) >= 4
        ):
            tokens.append(parts[-1])
        out[name] = tuple(tokens)
    return out


def find_characters_dir(start: Path) -> Path | None:
    """Find ``canon/characters`` above *start*."""
    current = start.resolve()
    if current.is_file():
        current = current.parent
    steps = 0
    while steps <= _MAX_WALK:
        folder = current / _CHARACTERS_REL
        if folder.is_dir():
            return folder
        if current.parent == current:
            break
        current = current.parent
        steps += 1
    return None


def load_cast(start: Path) -> tuple[CastMember, ...]:
    """Load character name and pronouns. Missing folders yield an empty cast."""
    folder = find_characters_dir(start)
    if folder is None:
        return ()
    names: list[str] = []
    rows: list[tuple[str, str]] = []
    for path in sorted(folder.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Could not read character file %s", path)
            continue
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        pronouns = str(raw.get("pronouns") or "").strip()
        names.append(name)
        rows.append((name, pronouns))
    tokens_for = _unique_tokens(names)
    cast: list[CastMember] = []
    for name, pronouns in rows:
        cast.append(
            CastMember(
                name=name,
                pronouns=pronouns,
                family=_family_for_label(pronouns),
                tokens=tokens_for.get(name, (name,)),
                path=str(path),
            )
        )
    return tuple(cast)


def cast_lines(cast: tuple[CastMember, ...], limit: int = 80) -> list[str]:
    """Short lines for a model: name and pronouns only."""
    lines: list[str] = []
    for member in cast[:limit]:
        if member.pronouns:
            lines.append(f"- {member.name}: {member.pronouns}")
        else:
            lines.append(f"- {member.name}")
    return lines


def _pattern(token: str) -> re.Pattern[str]:
    cached = _NAME_RE_CACHE.get(token)
    if cached is None:
        cached = re.compile(r"(?<!\w)" + re.escape(token) + r"(?!\w)", re.IGNORECASE)
        _NAME_RE_CACHE[token] = cached
    return cached


def named_in(text: str, cast: tuple[CastMember, ...]) -> list[CastMember]:
    """Return cast members whose name appears as a whole word in *text*."""
    found: list[CastMember] = []
    for member in cast:
        if any(_pattern(token).search(text) for token in member.tokens):
            found.append(member)
    return found


def _families(text: str) -> set[int]:
    found: set[int] = set()
    for word in re.findall(r"[A-Za-z']+", text):
        family = _pronoun_family(word)
        if family is not None:
            found.add(family)
    return found


def _drops_canon_name(old: str, new: str, cast: tuple[CastMember, ...]) -> bool:
    """True when the suggestion erases a character name that was in the excerpt."""
    if not new:
        return False
    for member in named_in(old, cast):
        if not named_in(new, (member,)):
            return True
    return False


def apply_cast(
    findings: list[Finding], cast: tuple[CastMember, ...]
) -> list[Finding]:
    """Use the cast on garbled findings.

    No cast: drop pronoun guesses, as before.
    With a cast: drop a note that erases a canon name. Keep a pronoun note
    only when the sentence names one person and the new pronoun matches
    that person's file. Never mark that note safe to paste.
    """
    if not cast:
        return drop_pronoun_guesses(findings)
    kept: list[Finding] = []
    for finding in findings:
        if finding.rule_id != "llm.garbled":
            kept.append(finding)
            continue
        old = finding.location.excerpt or ""
        new = (finding.suggestion or finding.replacement or "").strip()
        if _drops_canon_name(old, new, cast):
            continue
        if not is_pronoun_guess(old, new, finding.message):
            kept.append(finding)
            continue
        owners = named_in(old, cast)
        if len(owners) != 1 or owners[0].family is None:
            continue
        owner = owners[0]
        new_families = _families(new)
        old_families = _families(old)
        if owner.family in new_families and owner.family not in old_families:
            finding.applyable = False
            finding.replacement = None
            finding.metadata["cast_name"] = owner.name
            finding.metadata["cast_pronouns"] = owner.pronouns
            kept.append(finding)
            continue
        continue
    return kept


# Words that contradict a he/him or she/her character. "the girl" beside
# "his" is the chapter-12 case. They/them files are left alone.
_HE_FAMILY = 3
_SHE_FAMILY = 4
_PRONOUN_AGAINST: dict[int, re.Pattern[str]] = {
    _HE_FAMILY: re.compile(r"\b(she|her|hers|herself)\b", re.IGNORECASE),
    _SHE_FAMILY: re.compile(r"\b(he|him|his|himself)\b", re.IGNORECASE),
}
_NOUN_AGAINST: dict[int, re.Pattern[str]] = {
    _HE_FAMILY: re.compile(r"\b(girl|woman|lady|lass)\b", re.IGNORECASE),
    _SHE_FAMILY: re.compile(r"\b(boy|man|lad)\b", re.IGNORECASE),
}
_PROSE_FIELDS = (
    "backstory",
    "arc_summary",
    "dialogue_voice",
    "physical_description",
)
_LIST_FIELDS = ("history", "voice_wildcards")


def _clash_words(text: str, family: int | None) -> list[str]:
    """Pronouns and gendered nouns that contradict *family*."""
    if family not in _PRONOUN_AGAINST:
        return []
    words = [match.group(0) for match in _PRONOUN_AGAINST[family].finditer(text)]
    words.extend(match.group(0) for match in _NOUN_AGAINST[family].finditer(text))
    return words


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _record_text(raw: dict) -> str:
    chunks: list[str] = []
    for field in _PROSE_FIELDS:
        value = raw.get(field)
        if isinstance(value, str) and value.strip():
            chunks.append(value.strip())
    for field in _LIST_FIELDS:
        value = raw.get(field)
        if isinstance(value, list):
            chunks.extend(str(item).strip() for item in value if str(item).strip())
    notes = raw.get("voice_observations")
    if isinstance(notes, list):
        for note in notes:
            if isinstance(note, dict) and note.get("note"):
                chunks.append(str(note["note"]).strip())
    return "\n".join(chunks)


def canon_file_findings(start: Path) -> list[Finding]:
    """One note per character file that contradicts its own pronouns line."""
    folder = find_characters_dir(start)
    if folder is None:
        return []
    findings: list[Finding] = []
    for path in sorted(folder.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        pronouns = str(raw.get("pronouns") or "").strip()
        family = _family_for_label(pronouns)
        if not name or family is None:
            continue
        clashes: list[str] = []
        for sentence in _sentences(_record_text(raw)):
            words = _clash_words(sentence, family)
            if words:
                clashes.append(sentence)
        if not clashes:
            continue
        shown = clashes[0]
        if len(shown) > 220:
            shown = shown[:219].rstrip() + "…"
        findings.append(
            Finding(
                id="",
                category=Category.STYLE,
                severity=Severity.WARNING,
                message=(
                    f"{name}'s character file says {pronouns}, "
                    f"but the file also uses {', '.join(_clash_words(clashes[0], family)[:4])}."
                ),
                location=Location(
                    chapter_number=0,
                    chapter_path=str(path),
                    excerpt=shown,
                ),
                engine=Engine.DETERMINISTIC,
                rule_id="canon.pronoun_file",
                applyable=False,
                metadata={"cast_name": name, "cast_pronouns": pronouns},
            )
        )
    return findings


def chapter_pronoun_findings(
    chapter: Chapter, cast: tuple[CastMember, ...]
) -> list[Finding]:
    """Flag a sentence that names someone and then uses the wrong gender."""
    if not cast:
        return []
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for sentence in _sentences(chapter.content):
        owners = named_in(sentence, cast)
        if not owners:
            continue
        for member in owners:
            # Pronouns in a sentence often belong to someone else. A gendered
            # noun ("the girl" beside a he/him name) is the oversight.
            pattern = _NOUN_AGAINST.get(member.family or -1)
            words = [] if pattern is None else [m.group(0) for m in pattern.finditer(sentence)]
            if not words:
                continue
            key = (member.name, sentence)
            if key in seen:
                continue
            seen.add(key)
            label = ", ".join(dict.fromkeys(word.casefold() for word in words))
            findings.append(
                Finding(
                    id="",
                    category=Category.STYLE,
                    severity=Severity.WARNING,
                    message=(
                        f"{member.name} is {member.pronouns} in the character file, "
                        f"but this sentence also says {label}."
                    ),
                    location=Location(
                        chapter_number=chapter.chapter_number,
                        chapter_path=str(chapter.source_path),
                        excerpt=sentence if len(sentence) <= 280 else sentence[:279] + "…",
                    ),
                    engine=Engine.DETERMINISTIC,
                    rule_id="canon.pronoun_prose",
                    applyable=False,
                    metadata={
                        "cast_name": member.name,
                        "cast_pronouns": member.pronouns,
                    },
                )
            )
    return findings


__all__ = [
    "CastMember",
    "apply_cast",
    "canon_file_findings",
    "cast_lines",
    "chapter_pronoun_findings",
    "find_characters_dir",
    "load_cast",
    "named_in",
]
