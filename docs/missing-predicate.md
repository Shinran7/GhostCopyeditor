# Missing-predicate detection

GhostCopyeditor flags **period-terminated** sentences whose main clause has
**no finite verb** (no predicate). The Resonance Ch4 opener is the fixture:

> A rough chatter through Kieran's palm as he lifted the hauler clear of the buttress.

The subordinate *as he lifted…* has a verb. The main clause does not. The line
ends with `.`, so punctuation-only fragment sampling misses it.

## Install (optional NLP extra)

```text
uv sync --extra nlp
uv run python -m spacy download en_core_web_sm
```

Or: `task nlp-model` after sync.

Without spaCy / the model, companion and analyze still exit 0. Report
`warnings[]` includes:

```text
missing_predicate skipped: install ghostcopyeditor[nlp] and run: python -m spacy download en_core_web_sm
```

## Config flags (default-on)

```yaml
missing_predicate_enabled: true
missing_predicate_min_tokens: 5
missing_predicate_skip_dialogue_heavy: true
missing_predicate_typesafe_confirm: true
missing_predicate_require_period: true
```

Set `missing_predicate_enabled: false` to skip entirely (no missing-model warning).

## Signal

Shared API: `ghostcopyeditor.nlp.detect_missing_predicates`.

- Loud when ROOT is not finite **and** no finite `aux` / `auxpass` / `cop` child.
- Passive / perfect / copula / imperative stay quiet via that rule.
- Bare VBG / VBN roots (no finite aux) stay **loud** when the period gate passes.
- Resonance ROOT on `en_core_web_sm` 3.8.x: `chatter` / `NOUN` / `NN`.
- Dialogue suppress uses ASCII `"` only (curly quotes are an accepted miss in v1).
- Findings: `rule_id=mech.missing_predicate`, grammar WARNING, `applyable=False`.
- TypeSafe per-hit confirm may demote intentional hits to INFO (stay in findings).
- Combined per-hit TypeSafe budget (garbled + missing-predicate) = **12** asks per chapter.

## Autonomicon Editor

Editor calls the same API (`missing_predicate_detect.detect_missing_predicate_issues`).
Hits route to **isolated must-look** (`missing_predicate:` prefix), severity medium.
Import: `GHOSTCOPYEDITOR_ROOT` or sibling folder `GhostCopyeditor` on `sys.path`;
else soft-skip. Kill-switch: `AUTONOMICON_MISSING_PREDICATE=0`.

## Design

`docs/plans/design-d96237b7-missing-predicate.md`
