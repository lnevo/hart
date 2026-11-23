# Schematic solver on any plan: test plan (2026-11-23)

Status: parked (2026-11-23)

The schematic-maps plugin draws HART as approved in 38 s, but given HART as one continuous railroad (one input, no level cuts, no preferences) it needed a turnback cap it does not allow, then spent 43 minutes on rows and stopped with `columns: constraints do not settle` ([efficiency plan](../../docs/pipeline-map/efficiency-plan.md#full-rebuild-timed-2026-11-23)). The aim (owner, 2026-11-23): the plugin solves any AnyRail plan it is given, with no hand hints, in bounded time, and HART with the owner's layer files still comes out exactly as approved.

## Acceptance

1. **HART unchanged.** With the plugin branch, `make panels FULL=1` leaves `tables.xml`, both CATS desks, the schematic and station sheets byte-identical, and `check_approved.py` passes for `le-panel`, `cats-ctc` and `cats-abs`. The plugin's own goldens (`tests/golden/approved.json`, `baseline.json`) are unchanged.
2. **Any plan, no prompting.** Every plan in the test set (below) run with only its plan graph (`--no-preferences`, no plan overrides) ends in a time budget with either a drawing with 0 faults, or a drawing with its faults listed. It never hangs, never crashes with a traceback, and never asks for a setting such as "raise max_turnbacks".
3. **HART as one band.** The joined HART graph (staging and main spliced at the helix, no `levels` or `helix`) draws within the budget.
4. **Timed.** Every run records its time, cold cache, in a results table on this page.

**Where it stands (2026-11-23):** the owner chose the quick wins only after the baseline. Plugin [PR #86](https://github.com/lnevo/model-railroad-skills/pull/86) makes the reader cut the track at crossings, slips and turntables instead of crashing, and makes the solve fall back on `Unsettled` (F3) and raise the turnback cap by itself (F1). No plan ends in a traceback or asks for a setting now. HART is unchanged (set A). With a 2 minute row limit added from `one_band.py --row-seconds 120` (the plugin unchanged), HART draws as one band with no hints: one sheet, 2 crossings and 12 label faults, in 589 s, and the Layout Editor panel builds from it with 5 block contents icons left out; the CATS desk does not build (see "Set C drawn" below). Left: the time goes to the column placement, which runs again for every row arrangement tried, so F4 is that, not the row search alone; then F5 and the five set D plans with no orientation. The work is parked here until the owner picks it up again.

## What failed, and the fix to try for each

Found in the one-band run; each is checked by step 2 before it is changed.

| # | Fault | Fix to try |
|---|---|---|
| F1 | **Fixed in PR #86.** The turnback cap is fixed (3, or 5 on a plan with more than 40 switch-to-switch runs) and the run stops when it is too low | Raise the cap until an orientation is found, bounded by the plan's independent loops (edges minus nodes plus components) plus a margin; never stop on the cap alone |
| F2 | Orientations are tried in cost order even when the sweep already says a leg must cross other track (217B, 221B, 39 in the one-band run) | Run the sweep on each kept orientation first (cheap) and try those with no forced crossing before the others |
| F3 | **Fixed in PR #86.** `Unsettled` from the column placement ends the whole solve instead of moving to the next orientation | Catch it per orientation, log it, try the next; fail only when all have failed, with the best drawing and its faults |
| F4 | **Still open:** it alone keeps set C from drawing (2026-11-23 profile). The row search has no time limit | A budget per band (setting, default from the band's size) that returns the best rows found so far |
| F5 | The turnback search tries every combination of candidate runs | Only if step 2 shows it matters: prune by loops (each fold must break a cycle) before combining |

## Test set

| Set | What | Where it lives |
|---|---|---|
| A | HART with every layer file: the approved output | This repo (`make panels FULL=1`, `check_approved.py`) |
| B | HART raw: the two inputs, `--no-preferences` | This repo; commands in the efficiency plan |
| C | HART one band: the joined graph | Script `tools/schematic/experiments/one_band.py` (`--cap`, `--seconds`, `--profile`) |
| D | Other people's plans: about 10 AnyRail plans of different sizes and shapes (a shelf switcher, a loop with a yard, a dogbone, a two-level plan with a helix, a large club plan) | Local only, outside the repo: their track graphs are made with `schematic anyplan`/`plan`; the plans, and the objects and buildings in them, are other people's work and are not published |
| E | Made-up plans in the plugin's tests: the Pine Hollow & Eastern (`tests/example.py`) and new generated ones: random loops, ladders, reversing loops, crossovers, two levels joined by a helix | The plugin repo, public; generic, no HART names |

Set E is what keeps the fixes in the plugin: a fault found on a set D plan is reproduced as a small made-up plan in set E before it is fixed, so the public tests hold it without the private plan.

## Steps

Plugin work is on a branch of model-railroad-skills in its own worktree; HART only moves the submodule pin when step 7 passes.

| # | Step | Done when | Estimate |
|---|---|---|---|
| 1 | **Done 2026-11-23.** Baseline: run sets A to E on the current plugin (b0bc62ee), cold cache, each with its time and result; sets D and E under a 10 minute cap each | Results table below filled in | 1–2 h, mostly waiting; long runs on the Windows box (`make remote`) |
| 2 | **Set C done 2026-11-23** (below). Profile the one-band run (set C) and the slowest set D plan with `cProfile`: where the time goes in orient, rows and columns | The table above says which faults are real and where | 1 h |
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

## Owner's decisions (2026-11-23)

1. Set D: AnyRail's published sample layouts where they can be had; the owner may add plans later. The aim is a plugin that helps other people's plans, not only HART.
2. Time budget: 2 minutes for any plan up to HART's size, no hints, cold cache.
3. HART as one band stays a test case only; the approved three-band sheet is unchanged.

## Results

| Set | Plan | Before: time, result | After: time, result |
|---|---|---|---|
| A | HART approved | 431 s cold full rebuild, all steps pass (2026-11-23) | plugin 9d40e3a: byte-identical, all three approved fingerprints match; about 400 s cold (2026-11-23) |
| B | HART raw | solve 38 s, 0 faults; LE 1.5 s; CATS 0.2 s (2026-11-23) | |
| C | HART one band | orient 37 s (cap raised to 7, 6 turnbacks); rows 43 min; columns did not settle (2026-11-23) | no hints: the cap is raised by itself, orient about 24 s under the profiler; the row search still runs past 10 min (F4) |
| C | HART one band, plugin's own cap | 3.5 s: stops, `no orientation found; raise max_turnbacks` (F1) | see the row above: no stop on the cap |
| D | 38 AnyRail sample plans, JMRI exports | 13 drawn (3 to 31 switches, slowest 20 s; 12 with 0 faults, one reports "1 drawing faults" with an empty list); 2 stopped on the turnback cap (8 and 20 switches, F1); 21 stop in `plan` with a `KeyError` traceback at `plan_reader.py:147` (slips 12, crossings 7, turntables 3 counted with one other part); 2 stop on unsupported LH/RH crossovers | 27 drawn (20 with 0 faults, 7 with 1 to 6 faults listed; up to 39 switches, slowest 76 s); 8 clean errors (5 no orientation, two of them on the new 60 s search limit, 96 and 149 switches; 3 columns do not settle, 44 to 73 switches); 3 timeouts in the row search (53, 67 and 1077 switches); 0 tracebacks |
| E | Plugin tests (Pine Hollow & Eastern and the rest) | 764 tests pass in 91 s; slowest test 11 s | 780 pass in 99 s; new made-up plans for cut parts, crossovers of each hand, the cap raise and the `Unsettled` fallback |

Set D notes: the plans and the D-number to file mapping are local only (`~/Documents/Layout/anyrail-samples/`). `schematic anyplan` reads only 2 of the 38 `.any` files (the rest: no track end points found, older file layout), and it writes no graph, so the owner exported each plan from AnyRail as JMRI XML. Nothing above 31 switches got past the plan reader, so set D does not yet test the solver at HART's size.

## Set D: track left out, and the plans with no sheet (2026-11-23)

**Track left out.** The plan reader kept only the largest connected piece of track and dropped the rest without a word: 27 of the 38 samples lost 460 of their 2,395 switches. Most of the breaks were the cuts at crossings, slips and turntables (PR #86); a few were ends that nearly meet or truly separate track. Plugin [PR #87](https://github.com/lnevo/model-railroad-skills/pull/87) keeps every piece with a switch and draws each as its own band, joins ends up to 5 cm apart that face each other, and lists what it leaves out; a read with a section filter or height range (HART's) keeps the largest piece as before and lists the rest. HART's graphs and outputs are byte-identical. Crossings and slips are still cut, so those plans show many small bands with open ends.

**No sheet (11 plans).** Three groups:

| Group | Plans | Cause |
|---|---|---|
| No orientation | D35 (10 switches) | A balloon loop closed on a switch's through route (A to B): no legal facing exists |
| | D13, D7, D17 | Need turnbacks on straight runs, which the plans-over-40-runs filter (`udot > -0.5`) hides; with them they orient |
| | D10 | An orientation exists (15 turnbacks); the 60 s search limit stops first |
| Columns do not settle | D24, D38, D11 | Constraints that clash: a short siding read as a diagonal with level ends (D11), a short link forced to an exact span in a small ring (D24), two turnbacks at one switch that enclose each other (D38) |
| Time out in rows and columns | D34, D18, D6 | Size: the same as set C |

**Fix (plugin [PR #88](https://github.com/lnevo/model-railroad-skills/pull/88), merged 2026-11-23, pinned here).** Each fallback runs only when the usual path fails:
- an A-B balloon loop is drawn as two stubs beside the switch, with a warning;
- a second orientation pass, a seeded local search bounded by steps, runs when the first pass finds nothing, and shares the first pass's time limit;
- when no orientation of a band settles, the columns try once more with the clashing constraints relaxed, and each relaxation is listed as a drawing fault.

Results on set D, 240 s cap:
- D35 and D38 now draw.
- D14 draws a piece it left out.
- Every other plan that drew is byte-identical.
- D24 draws in about 10 min alone, still over the cap.
- D7, D11 and D13 get past orientation but run over the cap.
- D10 and D17 stop after about 70 s with "no orientation found".
- D6, D18 and D34 are size.

The six plans that remain are a speed problem, not a missing fallback, and stay parked with set C. Set A matches all three fingerprints; 818 plugin tests.

## Set C drawn (2026-11-23)

`one_band.py OUT --row-seconds 120 --panels`, plugin 1b108f7, cold cache, Mac. The sheet, the Layout Editor panel and the CATS desk come from one solve (`--panels` keeps it in a new cache folder inside OUT for the two panels). The script writes `one_band.svg` and `one_band_le.xml` in OUT; copies are in `~/JMRI_UserFiles/raw-experiment/` on the Mac as `HART_one_band_schematic.svg` and `HART_one_band_LE.xml` (wrapped in `layout-config` by hand, panel renamed "HART One Band"); nothing was deployed.

| Phase | Set A, approved | Set B, raw (three bands) | Set C, one band |
|---|---|---|---|
| Orientation | | | 11 s (the cap raised itself to 6 turnbacks) |
| Rows | | | 121 s in 21 optimisations: the limit (time inside the row optimisations only) was reached. An earlier run whose limit also counted the orientation and columns gave 65 s of rows and the same sheet byte for byte |
| Columns | | | 456 s in 1130 placements, about 0.4 s each |
| Sheet (`draw`) | 35 s | 38 s | 589 s; 2 crossings (near 221B and the 225 crossover), 12 label faults |
| Layout Editor panel | about 325 s with the preferences' passes | 1.5 s | 9 s; 5 block contents icons in the 201 to 211 area left out (205-201, 211B-211A, OS 207, 203-201, 207-203; `le` stops on them, the plugin's own `strict=False` lists them instead); the placed labels pass the plugin's label check |
| CATS desk | 2 s | 0.2 s | stops: double crossover 225's through tracks are not level beside it (rows 1 and 4), which CATS needs; forcing it means a plugin change |

The two crossings and the CATS stop come from the orientation, which the plugin had warned of (switches 221B and 39 each have a leg that must cross other track).

## Profile of set C (2026-11-23)

`one_band.py --cap 7 --seconds 600 --profile`, cold cache, Mac; cProfile slows the run about 2x.

| Phase | Time in 600 s | What it is |
|---|---|---|
| orient | 76 s (37 s without the profiler) | `orient.colour` called 971,712 times: every combination of up to 6 of 26 candidate runs. F5 is real. |
| rows | 335 s and not finished | `rows.descend_rows`, 13,500 row solves, 10.2 million `push_rows` calls; no limit (F4) |
| columns inside rows | 347 s, overlapping rows | `columns.place` runs for every row solve (`columns.cost` 120 s, `push` 3.3 million calls) |

The earlier 43 minute run ended in a `schematic.columns.Unsettled` traceback, not a clean stop (F3, and acceptance 2).
