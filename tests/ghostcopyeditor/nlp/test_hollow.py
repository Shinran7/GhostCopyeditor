"""Tests for hollow-imagery candidates."""

from __future__ import annotations

import pytest

import ghostcopyeditor.nlp.sentences as sent_mod
from ghostcopyeditor.nlp.hollow import hollow_candidates
from ghostcopyeditor.nlp.sentences import clear_cache


@pytest.fixture(autouse=True)
def _fresh() -> None:
    clear_cache()
    yield
    clear_cache()


def _patterns(text: str) -> list[tuple[str, str]]:
    return [(c.pattern, c.text) for c in hollow_candidates(text)]


def test_narrow_and_tail_shapes() -> None:
    text = (
        "Coolant knocked once in the pipe. Nobody filled the knock.\n\n"
        "She bit the biscuit and found the harbor's idea of supper.\n\n"
        "Harbor tar and cold leather rose, a smell with no opinion.\n\n"
        "He checked the hatch twice, a man reading a shelf.\n\n"
        "She walked to the door and opened it.\n"
    )
    got = _patterns(text)
    assert ("narrow", "Nobody filled the knock.") in got
    assert ("narrow", "She bit the biscuit and found the harbor's idea of supper.") in got
    assert ("narrow", "Harbor tar and cold leather rose, a smell with no opinion.") in got
    assert ("tail", "He checked the hatch twice, a man reading a shelf.") in got
    assert all("opened it" not in t for _, t in got)


def test_dialogue_skipped() -> None:
    assert hollow_candidates('"Nobody filled the knock," she said.\n') == []


def test_line_wrap_matches_and_offsets() -> None:
    text = "Intro line here.\n\nNobody filled\nthe knock.\n"
    (cand,) = hollow_candidates(text)
    assert text[cand.start : cand.end] == cand.text


def test_mind_subject() -> None:
    if sent_mod.get_nlp() is None:
        pytest.skip("spaCy model not installed")
    got = _patterns(
        "The archive considered the request for a long time.\n\n"
        "The door had opinions about the weather.\n\n"
        "The door had hinges.\n\n"
        "The clerk considered the request.\n"
    )
    assert ("mind", "The archive considered the request for a long time.") in got
    assert ("mind", "The door had opinions about the weather.") in got
    assert all("hinges" not in t and "clerk" not in t for _, t in got)
