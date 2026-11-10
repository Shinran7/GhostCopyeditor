# Cost & Budget Estimate

> All figures in **US dollars (USD)**. Loose ranges, not exact numbers.

## TL;DR

Local CLI for the Ghost suite. Typical month is API usage only (LLM + TypeSafe when enabled). Quiet months near $0 if engines stay off; busy novel passes can land in the tens of dollars depending on model choice.

## What you will need to sign up for

- LLM provider API key(s) for garbled/rewrite (same secrets pattern as Ghostreader) `(pay as you go)`
- TypeSafe.ai API key when TypeSafe judgments are enabled `(pay as you go)`
- No cloud host required for v1 (local CLI)

## Hosting & infrastructure

- **Hosting / app server**: $0 (local CLI)
- **Domain & TLS**: $0 for v1

## API & third-party fees

> Assumption: a few companion chapter runs per writing day; engines off by default until secrets exist.

- **AI / LLM (text)**: ~$0 - $40 / month depending on chapter volume and model
- **TypeSafe judgments**: ~$0 - $30 / month when enabled
- **Other**: $0

## Monthly band

- **Low** _(engines off / tests only)_: ~$0 / month
- **Typical** _(companion on a few chapters/day)_: ~$5 - $25 / month
- **High** _(full-novel analyze often + both engines on)_: ~$40 - $100 / month

## Scale considerations

- Whole-novel analyze with TypeSafe + LLM on every chapter pushes the high band
- Leaving engines off (defaults) keeps cost near zero
- Hollow-imagery judge: one LLM call per chapter (the whole chapter plus up to 80 candidate lines), on `hollow_judge` or the main model. Roughly the same tokens as one garbled pass. Turn off with `hollow_enabled: false`.
- Checked passage rewrites: two calls per passage (writer, then checker), capped at `rewrite_max_per_chapter` (default 8), so up to 16 calls per chapter. Each call is small (the passage plus three paragraphs on each side), but the writer is a prose model (e.g. Sol) and usually costs more than the analysis model. Rewrites run only when both `rewrite_writer` and `rewrite_checker` are set. Turn off with `rewrite_enabled: false` or `--no-llm`.

## Build & maintenance time

- **Build**: about 20 - 40 hours across the six design PRs
- **Maintenance**: about 1 - 3 hours / month after launch

## Decision point

### Decision recorded

- **Decision**: skip
- **Date**: 2026-09-21
- **Recorded by**: Shinran (via agent)
- **Reason**: Operator asked to implement immediately from the approved design doc; cost is not a gate for this hobby/suite-local CLI and mirrors Ghostreader spend patterns already in use.
