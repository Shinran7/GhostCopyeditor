# Autonomicon handoff

How Autonomicon can use GhostCopyeditor (GCE) without code changes on either
side breaking the other. Autonomicon is under code freeze; nothing here
requires an Autonomicon change today.

## What stays the same

- `from ghostcopyeditor.nlp import detect_missing_predicates` keeps its
  signature and its `MissingPredicateHit` fields. `tests/test_freeze_contract.py`
  fails if that changes.
- Autonomicon keeps its own checks (short-sentence stacks in `stilted_echo.py`,
  routing in `editor_routing.py`). GCE knows they exist; it does not replace them.
- GCE reports. Autonomicon fixes. `--apply` stays deterministic-only.

## The library call (when the freeze lifts)

```python
from ghostcopyeditor.api import check_chapter

result = check_chapter(
    chapter_text,
    chapter_number=4,
    path="chapters/chapter-04.md",
    story_dir="stories/the-farther-shore",  # optional: glossary + cast
    skip_rules=["echo."],                   # rule types Autonomicon already handles
)
result.findings   # action list: things a program may revise
result.may_look   # notes with no automatic fix
result.scenes     # per-scene counts and rhythm numbers
result.warnings   # e.g. spaCy model missing
result.api_version  # 1; bumped only on a breaking change
```

- Deterministic checks only by default: no API keys, no network.
- Pass `llm=<LangChain chat model>` and/or `typesafe_client=<AsyncTypeSafeClient>`
  to run those engines.
- Safe from sync code and from inside a running event loop.
  `check_chapter_async` is the async form.
- Each finding's `location` carries `char_start`/`char_end`, `scene` (1-based),
  and `sentence_start`/`sentence_end`, so a fix agent can target one sentence.

`skip_rules` matches by prefix. It can also be set in `config.yaml`.

## Suggested routing

| GCE rule prefix   | Goes to            | Why                                        |
| ----------------- | ------------------ | ------------------------------------------ |
| `mech.`, `word.`  | action list        | Small, safe, mostly applyable              |
| `llm.garbled`     | action list        | Confirmed corruption                       |
| `guide.banned`    | must-look          | Author's own banned list                   |
| `rhythm.`         | soft / punch list  | Craft note; needs a rewrite, not a fix     |
| `weak.`           | soft / punch list  | Density note; only fires over the limit    |
| `echo.`           | skip (Autonomicon has `stilted_echo`) |                         |

A finding with `metadata.rewrite_checked = true` carries a rewrite that GCE
re-checked (flag gone, no new problems, names and dialogue unchanged). Those
sit in the action list as `suggestion` severity, never auto-applied.
