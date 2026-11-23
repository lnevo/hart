# Schematic solver on any plan: test plan (2026-11-23)

Status: active

The schematic-maps plugin draws HART as approved in 38 s, but given HART as one continuous railroad (one input, no level cuts, no preferences) it needed a turnback cap it does not allow, then spent 43 minutes on rows and stopped with `columns: constraints do not settle` ([efficiency plan](../../docs/pipeline-map/efficiency-plan.md#full-rebuild-timed-2026-11-23)). The aim (owner, 2026-11-23): the plugin solves any AnyRail plan it is given, with no hand hints, in bounded time, and HART with the owner's layer files still comes out exactly as approved.

## Acceptance

1. **HART unchanged.** With the plugin branch, `make panels FULL=1` leaves `tables.xml`, both CATS desks, the schematic and station sheets byte-identical, and `check_approved.py` passes for `le-panel`, `cats-ctc` and `cats-abs`. The plugin's own goldens (`tests/golden/approved.json`, `baseline.json`) are unchanged.
2. **Any plan, no prompting.** Every plan in the test set (below) run with only its plan graph (`--no-preferences`, no plan overrides) ends in a time budget with either a drawing with 0 faults, or a drawing with its faults listed. It never hangs, never crashes with a traceback, and never asks for a setting such as "raise max_turnbacks".
3. **HART as one band.** The joined HART graph (staging and main spliced at the helix, no `levels` or `helix`) draws within the budget.
4. **Timed.** Every run records its time, cold cache, in a results table on this page.

## What failed, and the fix to try for each

Found in the one-band run; each is checked by step 2 before it is changed.

| # | Fault | Fix to try |
|---|---|---|
| F1 | The turnback cap is fixed (3, or 5 on a plan with more than 40 switch-to-switch runs) and the run stops when it is too low | Raise the cap until an orientation is found, bounded by the plan's independent loops (edges minus nodes plus components) plus a margin; never stop on the cap alone |
| F2 | Orientations are tried in cost order even when the sweep already says a leg must cross other track (217B, 221B, 39 in the one-band run) | Run the sweep on each kept orientation first (cheap) and try those with no forced crossing before the others |
| F3 | `Unsettled` from the column placement ends the whole solve instead of moving to the next orientation | Catch it per orientation, log it, try the next; fail only when all have failed, with the best drawing and its faults |
| F4 | The row search has no time limit | A budget per band (setting, default from the band's size) that returns the best rows found so far |
| F5 | The turnback search tries every combination of candidate runs | Only if step 2 shows it matters: prune by loops (each fold must break a cycle) before combining |

## Test set

| Set | What | Where it lives |
|---|---|---|
| A | HART with every layer file: the approved output | This repo (`make panels FULL=1`, `check_approved.py`) |
| B | HART raw: the two inputs, `--no-preferences` | This repo; commands in the efficiency plan |
| C | HART one band: the joined graph | Script `tools/schematic/experiments/one_band.py` (to write, from the scratch script of 2026-11-23) |
| D | Other people's plans: about 10 AnyRail plans of different sizes and shapes (a shelf switcher, a loop with a yard, a dogbone, a two-level plan with a helix, a large club plan) | Local only, outside the repo: their track graphs are made with `schematic anyplan`/`plan`; the plans, and the objects and buildings in them, are other people's work and are not published |
| E | Made-up plans in the plugin's tests: the Pine Hollow & Eastern (`tests/example.py`) and new generated ones: random loops, ladders, reversing loops, crossovers, two levels joined by a helix | The plugin repo, public; generic, no HART names |

Set E is what keeps the fixes in the plugin: a fault found on a set D plan is reproduced as a small made-up plan in set E before it is fixed, so the public tests hold it without the private plan.

## Steps

Plugin work is on a branch of model-railroad-skills in its own worktree; HART only moves the submodule pin when step 7 passes.

| # | Step | Done when | Estimate |
|---|---|---|---|
| 1 | Baseline: run sets A to E on the current plugin (b0bc62ee), cold cache, each with its time and result; sets D and E under a 10 minute cap each | Results table below filled in | 1–2 h, mostly waiting; long runs on the Windows box (`make remote`) |
| 2 | Profile the one-band run (set C) and the slowest set D plan with `cProfile`: where the time goes in orient, rows and columns | The table above says which faults are real and where | 1 h |
| 3 | Make the set E plans: one per fault seen in steps 1 and 2, each small enough to solve in seconds when fixed | Each fails on the current plugin for the reason found | 2 h |
| 4 | Fix F2 and F3 (orientation order, fall back on `Unsettled`), tests first | Set E's tests for F2 and F3 pass; set A byte-identical | 2 h |
| 5 | Fix F1 and F4 (cap from loops, row budget); F5 only if step 2 says so | Set C draws in the budget; set A byte-identical | 2–3 h |
| 6 | Run sets A to E again, cold cache, and fill in the after column | Acceptance 1 to 4 met, or the failures named | 1–2 h |
| 7 | Plugin PR (its own review), then move HART's submodule pin, `make panels FULL=1`, `check.sh`, `panelpro-test` | HART's outputs and fingerprints unchanged; no deploy needed | 1 h |
| 8 | Show the owner set C's sheet, Layout Editor panel and CATS desk on the Mac, and set D's sheets | Owner has looked | — |

Every step that changes plugin code reruns set A before it is committed: a change that moves one pixel of the approved drawing is reverted or the owner is asked.

## Rules for the work

- No HART names, plan file names or the owner's name in the plugin, its tests or its commit text (the plugin is public and generic: [REPOS](../REPOS.md)).
- No new setting the owner must fill in for HART: a new option defaults to today's behaviour on a plan HART's size, so set A needs no layer file change.
- A drawing with faults is a result, not a crash: it is drawn, with its faults listed, and the run exits non-zero only when asked to check.

## Decisions for the owner

1. Where set D's plans come from (AnyRail's sample layouts, plans the owner has, or both).
2. The time budget for a plan with no hints (suggested: 2 minutes for any plan up to HART's size).
3. Whether one band becomes something the HART sheet can use (a preference), or stays a test case only.

## Results

| Set | Plan | Before: time, result | After: time, result |
|---|---|---|---|
| A | HART approved | 431 s cold full rebuild, all steps pass (2026-11-23) | |
| B | HART raw | solve 38 s, 0 faults; LE 1.5 s; CATS 0.2 s (2026-11-23) | |
| C | HART one band | orient 37 s (cap raised to 7, 6 turnbacks); rows 43 min; columns did not settle (2026-11-23) | |
