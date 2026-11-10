# Monotony, weakeners, and checked rewrites

| Field | Value |
|-------|-------|
| **Date** | 2026-11-10 |
| **Status** | Done (slices 0–7 shipped on master) |
| **Issue** | Shinran7/GhostCopyeditor #2 |
| **Primary repo** | `C:\Users\shinr\Projects\GhostCopyeditor` |
| **Consumer** | `C:\Users\shinr\Projects\Autonomicon` (code freeze: no changes there yet) |
| **Related** | `docs/GhostCopyeditor-v1-System-Design.md`, `docs/plans/design-d96237b7-missing-predicate.md` |

---

## Overview

Recent models (Sol) write flat prose. Sentences come out short and the same shape: "She crossed the room. She opened the door. The air was cold." Today GhostCopyeditor catches grammar, garbled text, missing verbs, and echo. It does not notice flat rhythm.

Hemingway Editor Plus has useful tools: sentence flags, weakener counts, and AI rewrites it checks before offering. But its goal is shorter and simpler sentences. That is the opposite of what Sol needs. We take the tools and point them at **variety**.

This plan adds, in order:

1. A guard so the code freeze stays safe.
2. Sentence and scene positions on every finding.
3. One library function Autonomicon can call later.
4. A monotony check (the main new value).
5. A weakener check.
6. A style-guide section in config.
7. Checked rewrites.

Everything here only reports problems. Autonomicon does the fixing.

---

## The freeze rule (applies to every slice)

Autonomicon loads GhostCopyeditor straight from the sibling folder each time it runs (`Autonomicon\src\autonomicon\agents\missing_predicate_detect.py`). So any change here reaches Autonomicon right away, freeze or not.

- `detect_missing_predicates` keeps its name, arguments, and output.
- `MissingPredicateHit` keeps its fields.
- `ghostcopyeditor.nlp` keeps its current exports.
- New work goes in new functions and new files. We may add fields. We do not rename or remove any.
- The spaCy model must still load once. New checks reuse `get_nlp()` from `nlp/spacy_runtime.py`.

Slice 0 adds a test that fails if any of this breaks.

---

## Goals

1. Find flat rhythm in a scene and point to the worst runs.
2. Count weakeners per scene: qualifiers, filter words, adverbs on speech tags.
3. Put the scene number and full sentence on every finding.
4. Give Autonomicon one function that returns full findings.
5. Let Autonomicon say which problem types it already handles, so we don't report them twice.
6. Keep banned words, pet words, and preferred spellings in config.
7. Offer an AI rewrite only after it passes our own checks.

## Not doing

- Passive-voice flags and simpler-word swaps. Both push toward flat sentences.
- Reading grade, target grade, tone rewrites, heading and bullet tools.
- Moving any check out of Autonomicon.
- Applying any rewrite automatically. `--apply` stays deterministic-only.
- Any change inside Autonomicon during the freeze.

---

## Slices

Each slice lands on `master` with tests and passes `task check`. Coverage stays at 85% or higher.

### Slice 0. Freeze guard

**New:** `tests/test_freeze_contract.py`

- Pin the signature of `detect_missing_predicates` (argument names and defaults).
- Pin the fields of `MissingPredicateHit`.
- Pin the `ghostcopyeditor.nlp.__all__` list.
- Run the detector on the Resonance Ch4 opener and two quiet sentences. Pin the hits. Skip if spaCy is missing, as the current tests already do.

### Slice 1. Sentences and scenes

**New:** `ghostcopyeditor/nlp/sentences.py`

- `prose_sentences(text) -> list[Sentence]`. Each `Sentence` has a start, an end, a scene number, and flags for whether it is dialogue or narration.
- It uses spaCy when available, and falls back to a simple period, question mark, and exclamation split when not.
- It skips the same non-prose spans as today (frontmatter, code, headings, `---` breaks) from `checkers/regions.py`.
- It caches by text, so a chapter is parsed once even when several checks need it.

**New in `checkers/regions.py`:** `scene_spans(content) -> list[Span]`, split on the existing `---` scene-break pattern. Scenes are numbered from 1.

**Changed:** `models/finding.py`, `Location`. New optional fields: `scene`, `sentence_start`, `sentence_end`. They default to `None`, so old JSON readers still work.

**Changed:** `pipeline/runner.py`. One pass after IDs fills `scene` and the sentence span for every finding that has a position.

**Report:** each `ChapterResult` gets a `scenes` list: scene number, start, end, word count, and sentence count. Slice 3 adds rhythm numbers to it.

### Slice 2. Library function and caller-owned list

**New:** `ghostcopyeditor/api.py`

- `check_chapter(text, *, chapter_number=0, path="", config=None, use_llm=False, use_typesafe=False, skip_rules=()) -> ChapterCheck`
- `ChapterCheck` holds `findings`, `may_look`, `scenes`, and `warnings`.
- By default it is fast, needs no API keys, and runs the deterministic checks only. The LLM and TypeSafe are opt-in.
- It runs the existing chapter pipeline and makes no network calls by default.
- It is exported from `ghostcopyeditor/__init__.py` with `API_VERSION = 1`.

**Caller-owned rules:** a config list `skip_rules` plus an API argument of the same name. A finding is dropped when its `rule_id` starts with any listed entry. Autonomicon will pass its own list after the freeze.

**Doc:** `docs/autonomicon-handoff.md`. It describes the one-file change Autonomicon makes after the freeze. It also lists which Autonomicon checks overlap ours (for example its short-sentence stack check in `stilted_echo.py`, which flags 4 or more sentences in a row of 6 words or fewer). No Autonomicon code changes now.

### Slice 3. Monotony check (main value)

**New:** `ghostcopyeditor/nlp/sentence_shape.py` and `ghostcopyeditor/checkers/rhythm.py`

Narration sentences only. Dialogue is left out of the numbers, because speech is choppy on purpose.

**Per sentence, record:**

- Word count.
- Opening word, and opening type: pronoun, name, "the/a", -ing or -ed word, prepositional phrase, conjunction, adverb, or other.
- Whether it starts with subject then verb (subject first, main verb within the next three words).
- Clause count: the main verb plus joined or dependent verbs (spaCy `conj`, `advcl`, `ccomp`, `relcl`, `xcomp` on verbs).

**Per scene, compute:**

- Average sentence length, and how much length varies (spread compared with the average).
- Share of sentences that start with subject then verb.
- Share of the most common opening word.
- Share of sentences with two or more clauses.
- A variety score from 0 to 100 that combines the above. It is advisory only.

**Findings (new category `rhythm`):**

| Rule | Fires when | Location |
|------|-----------|----------|
| `rhythm.same_opener_run` | 3 or more narration sentences in a row open with the same word | the run |
| `rhythm.shape_run` | 4 or more in a row are single-clause, subject-then-verb, and similar in length | the run |
| `rhythm.flat_scene` | the scene's variety score is below the floor | the scene |

Messages state plain facts, for example: "Scene 2: 38 of 47 sentences open with subject then verb. Only 4 have more than one clause."

All numbers also go in `metadata`, so Autonomicon can set its own thresholds.

**Not covered here:** short-sentence stacks. Autonomicon already owns those. `rhythm.shape_run` needs the same shape, not just short length, so the two checks rarely overlap.

**Calibration step (part of this slice):**

1. Corpus: current chapters under `Autonomicon\stories\*\chapters\` (about 50 recent chapter files, mostly 1 or 2 per story). Archived drafts from other models (Gemini, Luna, Grok, DeepSeek) give a spread to compare against. Read-only. Nothing in Autonomicon is written.
2. Compute the scene numbers for every scene and write a table to a scratch file (not the repo).
3. Read the flattest and the most varied scenes by hand, and check that the score agrees with a reader's ear.
4. Set the defaults so the clearly flat scenes fire and the varied ones stay quiet.
5. Sanity check: run two public-domain novel chapters through. They should rarely fire.
6. Record the chosen numbers and the reasoning in the config comments.

All thresholds live in config (`rhythm_*` keys) and appear in `config.save()`.

### Slice 4. Weakeners

**New:** `ghostcopyeditor/checkers/weakeners.py`

| Rule | Examples | Where |
|------|---------|-------|
| `weak.qualifier` | seemed to, somehow, a little, almost, sort of, slightly | narration only |
| `weak.filter_word` | she felt, he noticed, she saw that, he realized | narration only |
| `weak.tag_adverb` | said softly, whispered quietly | speech tags next to dialogue |

- Narration only for the first two, because characters may hedge in speech.
- Each scene gets a count per 1,000 words in its `scenes` entry.
- A hit becomes a finding only when its scene is over the density limit. This keeps reports short when use is normal.
- Word lists live in the module and can be extended from config.

### Slice 5. Style guide in config

**New:** `ghostcopyeditor/checkers/style_guide.py`. New config block:

- `style_guide.banned`: a word or phrase list. Each hit is a warning.
- `style_guide.pet_words`: word to per-chapter limit. A note when the limit is passed.
- `style_guide.spellings`: wrong to right. Applyable with `--apply`, but skipped for protected lexicon terms.

Lexicon and cast protection run after this check, as they already do for other checks.

### Slice 6. Checked rewrites

**New:** `ghostcopyeditor/llm_engine/rewrite.py`, run after the other engines in `pipeline/runner.py`.

1. Choose findings that need a rewrite: `rhythm.*` runs and `weak.*` hits. Cap at `rewrite_max_per_chapter` (default 8). Worst first.
2. Make one LLM call per scene. Send each flagged span with two sentences of context on each side, and give a direct instruction: vary the openings, join into one longer sentence with a dependent clause, or drop the qualifier.
3. Ask for up to two candidates per span.
4. Check each candidate by placing it in the scene text and re-running our deterministic checks on that scene. Keep it only if:
   - the original flag is gone;
   - no new finding appears in that span;
   - the scene variety score does not drop;
   - protected lexicon and cast names are unchanged (reuse `lexicon.py` / `canon.py`);
   - dialogue inside quotes is unchanged;
   - the length change stays within bounds (default plus or minus 40%).
5. When a candidate passes, it becomes `suggestion`, and `metadata.rewrite_checked = true`. `applyable` stays false.
6. When none pass, the finding stays as it is, with `metadata.rewrite_checked = false`.

This runs only when the LLM is on (not `--no-llm`). It is off by default in `api.check_chapter`. Update `COST-ESTIMATE.md` with the extra calls.

**Superseded (2026-11-10).** Sentence rewrites from one analysis model shuffled synonyms and added hollow images. Slices 8 to 10 replace this slice.

### Slice 7. Docs

- Update `docs/GhostCopyeditor-v1-System-Design.md`: new categories, new rules, and the `scenes` report block.
- Update the JSON golden file `tests/fixtures/golden_companion_report.json`.
- Finish `docs/autonomicon-handoff.md` with the final rule names and suggested routing:
  - `rhythm.*` and `weak.*` go to Autonomicon's soft or punch list.
  - `guide.banned` goes to must-look.

### Slice 8. Hollow-imagery notes

Code finds candidate sentences (narrow phrases, closing appositive tags, objects with a mind). One LLM judge call per chapter confirms them. Notes only (`hollow.image`, `may_look`).

### Slice 9. Per-job models

`hollow_judge`, `rewrite_writer`, `rewrite_checker` in config, each with model, temperature, max_tokens, reasoning_effort. The model that analyzes is not the model that writes. Rewrites use the book's writing model (Sol) or another proven prose model.

### Slice 10. Checked passage rewrites

The unit is one or two flagged paragraphs, with three paragraphs of context, the cast, and the lexicon. The writer edits for purpose and may cut. Then GCE's own checks run, then a checker model lists literal facts (kept / changed / lost) and facts added, apart from wording notes. Any literal fact change rejects the edit. Each kept edit is one `rewrite.passage` finding. Live result: 4 of 7 kept on Autonomicon chapter 1. Details: system design, "Checked passage rewrites".

---

## Decisions (locked 2026-11-10)

1. **Notes list by default.** Rhythm, weakener, and hollow findings go in the `may_look` notes list, like echo. Checked edits are separate `rewrite.passage` findings in the action list (revised with Slice 10).
2. **Calibration corpus.** Recent chapters under `Autonomicon\stories\`. Most show the monotony. Two public-domain chapters serve only as a sanity check.
3. **Rewrites on by default** in companion and analyze, capped at 8 per chapter. `--no-llm` turns them off. The library function keeps them off unless asked.

---

## Risks

- **spaCy tagging errors.** Wrong tags can miscount subjects and clauses. The scene-level numbers absorb single errors. The run rules need 3 to 4 sentences in a row, which also limits noise.
- **Threshold drift across models.** Sol today, another model later. Keep every limit in config, and keep the raw numbers in `metadata`.
- **Freeze breakage.** This is covered by Slice 0 and the freeze rule.
- **Rewrites that make things flatter.** Sol cuts decoration hard and can go flat. The checker's `wording` notes say what was lost; the caller decides.
- **Continuity.** The book reads its own earlier chapters, so a lost fact is the worst failure. The checker rejects any literal fact change; false rejections are the accepted cost.
