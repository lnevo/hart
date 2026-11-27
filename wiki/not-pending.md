# Not pending

Items the owner has said never to list as pending, to re-raise or to report, with the rule for each and where the item is recorded instead.

The `whats-left` skill reads this page and drops everything it excludes. Add a row when the owner gives a new "never list this" rule; chat memory is not shared between sessions, this page is.

## Parked features

| Item | Rule | Recorded instead | Owner date |
|------|------|------------------|------------|
| Entry/Exit (NX), the stock Dispatcher System, the USS CTC machine | Never list as a to-do. Unparking is the owner's call. | `jmri/layouts/hart/parked/`, [`docs/parked/UNPARK.md`](../docs/parked/UNPARK.md) | 2026-11-17 |
| Warnings that come only from a parked element (launcher warnings on parked tables, refreshing `tables_parked.xml`, swapped USS icons, stale Digicon-era names in parked docs) | Do not fix or report as a finding; add to the unpark doc. | [`docs/parked/UNPARK.md`](../docs/parked/UNPARK.md) | 2026-11-21 |
| Occupancy lamps and station clusters on the Layout Editor panel | Part of the parked Dispatcher. Never list lamp placement as a loose end; do not fix, test-pin or rework it. A lamp-offset check is skipped with that reason, not loosened. | `jmri/layouts/hart/parked/` | 2026-11-21 |
| Five USS CTC redraw leftovers: masts 4RA, 4RB and 2L facing differently from the CATS desk; signal icons over the OS jewel edge at switches 7, 23a and 33; six pairs of touching jewels; the Windows apply skipping the Start Up retarget with a warning when no Python is found; the permission-mode notice | Accepted as they are. Never list as pending; revisit only if the owner raises one. | `FACING_EXCEPTIONS` in `test_ctc_signal_heads.py`; [`docs/parked/UNPARK.md`](../docs/parked/UNPARK.md) | 2026-11-11 |
| The old Dispatcher "facing direction inverted" story | It was a wrong setting, not a stock bug or a mast issue. Keep it off the site and guides. | History only in [`STATUS_LOG.md`](STATUS_LOG.md) | 2026-11-12 |

## Owner decisions not to re-raise

| Item | Rule | Recorded instead | Owner date |
|------|------|------------------|------------|
| New cars and locomotives to photograph or take in (intake) | Never list as outstanding or backlog; the owner starts intake when ready. | Runbook in [`pipelines/intake-stages.md`](pipelines/intake-stages.md) | 2026-11-09 |
| Periodic LCOS subscription replay proposal (event 125) | Dropped. Never list or revive from old docs; check `STATUS_LOG.md` before moving old open items into live pages. | [`STATUS_LOG.md`](STATUS_LOG.md) | 2026-10-31 |
| Camera car identification (OCR plus image comparison) | Written up, never a to-do. Pick up only when the owner raises it. | [`docs/ops/CAMERA_CAR_ID.md`](../docs/ops/CAMERA_CAR_ID.md) | 2026-11-16 |
| Web server move leftovers: deleting the old server's final snapshot, the panel's own certificate, mail for one of the other hosted sites, a cloud budget alarm (names in the owner's private notes) | The move is closed. Never list these as pending; take one up only if the owner raises it. | private notes | 2026-11-23 |
| A pipeline-map check that flags hovered lines lighting 50 or more boxes (untagged hubs, side links or runners) | Built only if the map gets noisy again. Never list as pending. | None; the hover stop rules are in `tools/ops/pipeline_map_layout.js` | 2026-11-22 |
| CATS label edge cases from the schematic-maps plugin (title fallback row, `trim_columns`, `--band` page prefs, two window validators, `--window` alone) | Nice-to-have. Never list; take up only if the owner asks or a desk hits one. | None; not tracked | 2026-11-18 |
| `signal_coordinator.py` blocking `runOnLayout` (the 30 s bulk-set timeout cannot fire live) | Accepted. Never list; revisit only if a hang is actually seen. | None; not tracked | 2026-11-20 |
| Scale track and OS 7 detector gap (23 cm of Scale on OS 7's detector) | Matters only for speed profiling. Never list as a follow-up or mismatch; never suggest moving the rail gap. | Level unification step 5 in [`level-unification-handoff.md`](../archive/history/wiki/projects/level-unification-handoff.md) | 2026-11-20 |
| Diamond P&OC herald on the Railroads 2000-2008 lineage card | Kept by the owner's choice. Do not flag it as an error or propose a wordmark. | None; not tracked | 2026-11-12 |
| Link card for the speed-runs article on the AI hub page | Rejected. Do not propose hub cards for single articles or list this as a website item. | The article is linked from the Locomotives topic only (`www/ai/speed-runs.html`) | 2026-11-18 |
| MRE Electrical SOQ | Submitted and frozen, and out of the pipeline (owner, 2026-11-22). Never rebuild, refill or "tidy" it or its inputs, and never list its build as broken. Evaluator changes are one-off hand edits, noted in `SUBMITTED.md`. Its tests were removed and nothing builds or tests it (owner, 2026-11-25). The layout documentation page is maintained on its own and follows the live data. | [`docs/ap/electrical/SUBMITTED.md`](../docs/ap/electrical/SUBMITTED.md) | 2026-11-15 |
| LCOS mimic publishing fake feedback on the Pi's live broker | Accepted. Never list as a risk or loose end; do not propose a separate broker for the owner's environments. | None; not tracked | 2026-11-12 |
| Site wording about JMRI and CATS | Say they are stock installs as plain fact. Never "almost stock", and no sections that defend the approach. | None; a writing rule | 2026-11-12 |
| Helix-top intermediate signals (A75/B75) | Dropped; the home signals at 127 and 131 (129 and 135 before the 2026-11-19 renumber) govern the helix. Never list or re-propose them. | [ADR-024](decisions/ADR-024-signals-by-rule.md) (ADR-031 superseded) | 2026-11-19 |
| The Main West turnback (AnyRail draft 3) | Dropped and its branch deleted. Never propose it again. | [ADR-026](decisions/ADR-026-anyrail-5-3c-master-plan.md) | 2026-11-20 |
| Further Layout Editor text-size steps (condensed-font metrics, helix label size, step C3) | Dropped after step C1 and the 14 px station names shipped (#898). The topic is closed; never list or propose it. | None; not tracked | 2026-11-21 |
| Stock JMRI and CATS operating risks (MQTT startup race, CATS load risk) | Leave out of any "what is pending" answer. They are standing notes, not open work. | Operating notes in [`status/current/`](status/current/) (`mqtt-startup-race.md`, `cats-load-risk.md`) | 2026-11-01 |
| CPython repo tools in `jmri/layouts/hart/scripts/` beside the Jython scripts JMRI runs (19 of 39 files on 2026-11-23) | Leave them there; do not propose moving them. | Architecture review of 2026-11-23 (`wiki/STATUS_LOG.md`) | 2026-11-23 |
| An audit that a Jython script never imports `hartlib` | Not needed; do not propose it. The rule stays in AGENTS.md and the scripts' comments. | Architecture review of 2026-11-23 (`wiki/STATUS_LOG.md`) | 2026-11-23 |

## Future goals

| Item | Rule | Recorded instead | Owner date |
|------|------|------------------|------------|
| Operations Pro build follow-up (R1-R8, plugin fixes P1-P19) | Side project. List only under future goals; do not raise R2 or the follow-up list in what's-next answers. | [`docs/ops/OPSPRO_FOLLOWUP.md`](../docs/ops/OPSPRO_FOLLOWUP.md); "Future goals" in [`status/future/`](status/future/) | 2026-11-21 |
| LCOS bridge move to the Pi | Future goal, not next. | "Future goals" in [`status/future/`](status/future/) | 2026-11-21 |
| Speed matching follow-ups (decoder read-back, loop 2 lap survey) | Future goal, not next. | "Future goals" in [`status/future/`](status/future/); [`projects/speedmatching.md`](projects/speedmatching.md) | 2026-11-21 |

## Watch-only items

| Item | Rule | Recorded instead | Owner date |
|------|------|------------------|------------|
| Power districts and terminal blocks (the empty Power District column in the LCOS inventory, the unverified `docs/wiring/terminal_blocks.md`) | Not important for now. Never list them as data gaps or to-dos in the data-masters work. | None; not tracked | 2026-11-25 |
| Pi LCC serial write timeouts right after PanelPro shutdown | Ignore. Report LCC serial trouble only if it shows while JMRI runs, or if a shutdown hangs and needs a kill. | None; not tracked | 2026-11-12 |
| WiThrottle "null readLine()" warnings on the Pi every 5 minutes | From the Mac's own netmon.py cron (outside the repo) probing port 12090; harmless. Never list or chase it. | None; not tracked | 2026-11-27 |
