# HART Operations Pro: what is outstanding after the build

Written 2026-11-02 after the owner's review of the build on branch `agent/claude/opspro-build` (PR #120). Three lists: what the railroad still needs, what the plugin needs, and why the audit findings that remain are not a to-do.

## 1. The railroad

| # | Item | Who | When |
|---|---|---|---|
| R1 | Merge PR #120 and deploy with `./cats/scripts/sync_hart_package.sh --pi`. The Pi's previous files are saved in [`archive/operations-pi-2026-11-02/`](../../archive/operations-pi-2026-11-02/) | owner | next |
| R2 | Run the `Session` automation on the Pi with the plugin's live lane (`ops_install_agent`, then `ops_live_automation`), through one real session. The ordered test on copies proved the order; a live JMRI has not run it | owner with an agent | first session after deploy |
| R3 | Replace the 60 ft per spot (70 at A. Stucki) with measured spur lengths, and the halved South Yard lengths with the real split, when the main level is built | owner | main level |
| R4 | Place the 29 unplaced cars if they should enter service: 10 no-photo freight cars and HART 1776 can go to South Yard as empties; the passenger cars and cabooses need a track that takes their types | owner | any time, `place_car` |
| R5 | Watch the two Steel Plate flatcars that started loaded with no final destination: they went offline once and come back as Steel for A. Stucki. Expected, but check after session 1 | agent | after session 1 |
| R6 | Tune move counts after two or three real sessions: the STG trains' 30 moves, NVL's industry moves (8/3/4/5/5/3) and the random 50 on the IX lines were set by reasoning, not by running | agent | after session 3 |
| R7 | Keep the car repository and the roster in step as mapping section 10 proposes: `bin/cars publish` derives the Operations type from the STS code and the coke-fleet list, adds cars with no location, and `bin/cars compare` reports type, length and weight differences | agent | separate job |
| R8 | Retire `docs/ops/opspro-build/ordered_session.py` once the plugin's dry run can order trains (plugin item P4 below) | agent | with P4 |

## 2. The plugin

25 faults were recorded in [`opspro-build/plugin_faults.csv`](opspro-build/plugin_faults.csv) and none was patched during the build. They need a fixes pass in `external/model-railroad-skills`, like the one that followed the showcase ([`OPSPRO_PLUGIN_FIXES_PROMPT.md`](OPSPRO_PLUGIN_FIXES_PROMPT.md)). Grouped by what they cost, worst first.

**Silent wrong results (fix first)**

| # | Fault | Evidence | Fix |
|---|---|---|---|
| P1 | `add_route` stop fields `pickups` and `drops` given as the strings "yes" and "no" are dropped without an error; the diff shows both yes | F9, stage 2C | Refuse a non-boolean, or accept yes/no |
| P2 | `add_industry` names the schedule `<spur> Schedule` and returns an existing schedule of that name, so two industries with a spur called Chemical Unload share one schedule and the second industry's lines are dropped silently | F13, stage 3A | Take a `schedule` name field, and refuse a name that exists unless told to share |
| P3 | `add_train` refuses an engine road or a new engine model until an engine exists; the build order in SKILL.md puts trains before locomotives | F10, stage 2C | Allow the fields, warn, or reorder the skill |

**Cannot test a session**

| # | Fault | Evidence | Fix |
|---|---|---|---|
| P4 | `ops_dry_run` builds every train from one start state, not in departure order, with no terminate between trains, so hand-offs and interchange room are never exercised; it says it runs the startup automation but its result has no automation trace, and an ordered replay set as startup showed no hand-off | F22, F24, stages 4 and 5 | An `order` option: a list of jobs (trains to build, then terminate) run in sequence on one copy, which is what `opspro-build/ordered_session.py` does with `run_worker` |
| P5 | `ops_dry_run` at normal detail returns about 150 KB for five trains and spills to a file | F19 | Summary by default; per-train calls |
| P6 | The worker's `log_errors` lists JMRI's own "Schedule missing for car ... to spur (Off Spot)" lines, which JMRI writes for a correct overflow to an alternate | F25 | Filter or explain them |

**Missing actions and fields**

| # | Fault | Evidence | Fix |
|---|---|---|---|
| P7 | No action sets the railroad name on a blank file; the workaround is `set_train_manifest` on every train | F3 | `set_option` for the railroad name |
| P8 | No action changes a car's type; delete and re-add | F17 | `update_car type` |
| P9 | `add_industry` has no pick up or set out list fields | F14 | Add them |
| P10 | `add_track` refuses `hold_custom` on a spur with no schedule, so a spur cannot be held before its schedule exists | F7 | Allow it, or say so in `add_industry` |
| P11 | `setup_interchange` takes plain lists where `add_track` takes `{option, names}`, and has no way to say All for destinations | F11 | One shape |
| P12 | `set_startup_automation` says "or none" but refuses the word; an empty string clears it | F23 | Accept none |

**Output and help**

| # | Fault | Evidence | Fix |
|---|---|---|---|
| P13 | `ops_actions` with no action fails with a JSON serialization error | F1 | Return the list |
| P14 | `ops_actions` omits fields an action accepts (`load` on `update_car`) and `add_engine` wants location plus track where its help suggests a track name | F15, F16 | Regenerate the field lists from the signatures |
| P15 | `ops_list` shows no settings (buildOptions, router), no train description, time or comment, no locomotive types on tracks, and car locations as ids; its car filter does not match location names | F4, F8, F12, F18, F20 | A `settings` type; names beside ids; filter on location |
| P16 | `set_option` scale wants JMRI's index (6 for HO) and nothing lists it | F2 | Accept the scale name |
| P17 | A plan with many findings prints every finding in full, twice | F5 | Count per rule with one example |
| P18 | `ops_why_not` with `failing_only` still prints every not_checked gate | F21 | Drop them too |
| P19 | The first `ops_apply` on a blank folder returns an empty backup name | F6 | Cosmetic |

Handoff: give the fixes pass `plugin_faults.csv`, this section, and the 22 lessons in [`opspro-build/lessons.csv`](opspro-build/lessons.csv); the lessons that belong in SKILL.md are L3, L5, L7, L8, L12, L14, L15, L18, L19 and L20. Run the plugin's own tests before and after, and re-run `opspro-build/ordered_session.py` against this folder afterwards to confirm nothing in the build path changed.

## 3. The audit findings that remain

Nothing here is a defect. They stay because of decisions the owner confirmed.

| Rule | Count | Why it stays | Goes away when |
|---|---|---|---|
| type-no-track | 5 | Baggage, Coach, Combine, Dining and Observation exist for the unplaced passenger cars (D24) | R4 places them on a track that takes the types |
| car-unplaced | 29 | Cars STS does not position start with no location (D24) | R4 |
| route-stop-dead | 1 | CK1's Scale stop weighs the coke pull and does no work (D1) | never; it is the design |
| train-not-on-list | 4 | D749 only sets out and D749 Return only pulls at Demmler; only CK1 pulls K-1 and K-2 (D9) | never; they are the restrictions |

If the passenger cars stay unplaced for good, the five `type-no-track` errors can be silenced by giving S-R those five types, which costs nothing while the cars have no location.
