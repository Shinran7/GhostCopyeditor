# SLizard Self-Audit Triage Outcome

- Total findings: 16
- Verified bugs to fix: 2
- Reporting debt: 14
- Wontfix candidates: 14
- Still pending: 0

## 1. BUGS WE NEED TO FIX

- **P1** `ghostcopyeditor/api.py:154` — ghostcopyeditor/api.py:154–158 — Async callers passing loop-bound clients can fail when check_chapter runs their work on a new event loop. Failure: client requests may raise a different-loop error or hang. (likely-bug: api.py:149-157 runs check_chapter_async under a fresh asyncio.run (worker thread when a loop is running) on every call, so caller-supplied async llm/typesafe_client/role_llms reused across calls or created on the caller's loop get driven on a foreign or closed loop; failures then surface as swallowed errors (hollow.py:107-111 returns []). Docstring at api.py:129 promises loop safety. P1 is high; check_chapter_async is the escape hatch.)
- **P2** `ghostcopyeditor/pipeline/runner.py:145` — ghostcopyeditor/pipeline/runner.py:145–159 — Callers using skip_rules can still receive rewrites triggered by skipped findings. Failure: a skipped rhythm, weakener, or hollow note can cause a rewrite before the note is removed. (confirmed-bug: runner.py:164-166 runs run_passage_rewrites on findings before drop_skipped_rules at runner.py:172. _units (rewrite.py:139-145) picks rhythm/weakener/hollow triggers regardless of skip_rules, and the emitted rule_id 'rewrite.passage' (rewrite.py:377) is not dropped. So skip_rules=['rhythm'] with rewrites=True still costs LLM calls and returns rewrites for skipped notes.)

## 2. POOR REPORTING IN SLIZARD

### overstated (7)
- `ghostcopyeditor/checkers/anachronism.py:66` — anachronism.py:75 sets one chapter-wide earthish flag from _EARTH_SETTING_CUES and line 86-88 skips every hit by design ('Intentional Earth POV'); the checker is a report-only SUGGESTION, so chapter-level suppression is a coarse heuristic, not a P1 failure.
- `ghostcopyeditor/report/json_export.py:139` — json_export.py:139-154: rollback re-writes saved text and re-raises. A rollback write can only fail if the disk fails again right after the first failure, and there are at most two paths (canonical plus -o). Not all-or-nothing in theory, negligible in practice.
- `ghostcopyeditor/llm_engine/hollow.py:118` — hollow.py:118-121 deliberately falls back to the candidate sentence span when the LLM's phrase is not found; the finding is still emitted with sentence metadata (lines 135-140). The broader span is a reasonable fallback, not a P1 defect.
- `ghostcopyeditor/pipeline/positions.py:36` — positions.py:30-35 falls back to sentences[first].end only when char_end-1 lies outside any prose sentence (sentences.py:118-124), such as a gap or non-prose. Using the starting sentence's end is a deliberate approximation that still yields a valid sentence span.
- `ghostcopyeditor/llm_engine/hollow.py:95` — hollow.py:108 awaits llm.ainvoke with no wait_for; timeouts are the caller-supplied LangChain client's job (its own request timeout), and errors are caught at lines 109-111. This is a hardening niggle, not a blocking defect.
- `ghostcopyeditor/checkers/echo.py:326` — echo.py:329-335 drops skipped tokens and joins the rest of a blank-line paragraph, but non_prose spans (headings, fences, scene breaks per regions.py:80-81) rarely sit inside one paragraph with prose on both sides, and the gap must also be within max_gap. A rare SUGGESTION-level false positive.
- `ghostcopyeditor/checkers/echo.py:220` — echo.py:343 uses the whole paragraph as the excerpt while the offsets (line 354) cover the matched span; the message names the phrase (line 350) and the finding is applyable=False, so there is only a cosmetic excerpt mismatch.

### false-positive (3)
- `ghostcopyeditor/models/report.py:178` — report.py:161-186 sends every finding in the ECHO/RHYTHM/WEAKENER/HOLLOW categories to may_look via _NOTE_CATEGORIES; the rule_id set only adds echo ids. There is no validator in report.py, and rhythm/weakener/hollow notes do not leak into the action list.
- `ghostcopyeditor/report/json_export.py:148` — json_export.py:148-154: the except Exception handler rolls back and then re-raises with a bare raise at line 154, so nothing is swallowed.
- `ghostcopyeditor/llm_engine/rewrite.py:203` — rewrite.py:255 bounds the 'after' range with unit.start+len(edit), using the same stripped edit spliced in at line 253; 'before' is compared on the original unit.start..unit.end (line 256), and both runs use _strict_cfg (line 413). No stale offset.

### speculative (3)
- `ghostcopyeditor/typesafe/missing_predicate_review.py:84` — missing_predicate_review.py:84,110-116 mutates finding.metadata/severity in place, but the only caller (runner.py:149) uses findings it just built and keeps the returned list; no repo path reuses or discards a reviewed result.
- `ghostcopyeditor/typesafe/per_hit_budget.py:1` — The only production caller (runner.py:136,146,156) creates one PerHitAskBudget per chapter and passes it to both reviews; budget=None or separate instances only arise from hypothetical external callers.
- `ghostcopyeditor/nlp/spacy_runtime.py:21` — spacy_runtime.py:21-34 has no lock, but nothing in the repo calls get_nlp concurrently: the only thread use is api.py:153 (one worker per call), and the pipeline is single-threaded async. A duplicate load needs an external multithreaded host and is transient anyway.

### duplicate (1)
- `ghostcopyeditor/report/json_export.py:139` — Same anchor and message as 6c8ea8a355985c23 (json_export.py:139-154). Nothing in the repo writes the same report path concurrently, so the 'concurrent overwrite' category has no code path either.


## 3. WONTFIX CANDIDATES

- `ghostcopyeditor/models/report.py:178` — report.py:161-186 sends every finding in the ECHO/RHYTHM/WEAKENER/HOLLOW categories to may_look via _NOTE_CATEGORIES; th
- `ghostcopyeditor/report/json_export.py:148` — json_export.py:148-154: the except Exception handler rolls back and then re-raises with a bare raise at line 154, so not
- `ghostcopyeditor/typesafe/missing_predicate_review.py:84` — missing_predicate_review.py:84,110-116 mutates finding.metadata/severity in place, but the only caller (runner.py:149) u
- `ghostcopyeditor/checkers/anachronism.py:66` — anachronism.py:75 sets one chapter-wide earthish flag from _EARTH_SETTING_CUES and line 86-88 skips every hit by design 
- `ghostcopyeditor/report/json_export.py:139` — json_export.py:139-154: rollback re-writes saved text and re-raises. A rollback write can only fail if the disk fails ag
- `ghostcopyeditor/llm_engine/hollow.py:118` — hollow.py:118-121 deliberately falls back to the candidate sentence span when the LLM's phrase is not found; the finding
- `ghostcopyeditor/typesafe/per_hit_budget.py:1` — The only production caller (runner.py:136,146,156) creates one PerHitAskBudget per chapter and passes it to both reviews
- `ghostcopyeditor/nlp/spacy_runtime.py:21` — spacy_runtime.py:21-34 has no lock, but nothing in the repo calls get_nlp concurrently: the only thread use is api.py:15
- `ghostcopyeditor/pipeline/positions.py:36` — positions.py:30-35 falls back to sentences[first].end only when char_end-1 lies outside any prose sentence (sentences.py
- `ghostcopyeditor/llm_engine/hollow.py:95` — hollow.py:108 awaits llm.ainvoke with no wait_for; timeouts are the caller-supplied LangChain client's job (its own requ
- `ghostcopyeditor/llm_engine/rewrite.py:203` — rewrite.py:255 bounds the 'after' range with unit.start+len(edit), using the same stripped edit spliced in at line 253; 
- `ghostcopyeditor/checkers/echo.py:326` — echo.py:329-335 drops skipped tokens and joins the rest of a blank-line paragraph, but non_prose spans (headings, fences
- `ghostcopyeditor/report/json_export.py:139` — Same anchor and message as 6c8ea8a355985c23 (json_export.py:139-154). Nothing in the repo writes the same report path co
- `ghostcopyeditor/checkers/echo.py:220` — echo.py:343 uses the whole paragraph as the excerpt while the offsets (line 354) cover the matched span; the message nam