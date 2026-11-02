# Plugin faults from the showcase build

**Resolved.** Every item below was fixed or settled in the plugin by 2026-11-02, and the full suite last passed 778 tests on JMRI 5.16. The rest of this page is the original report, kept as history. Its line numbers and test count are from before the fixes, and `faults.csv` has the resolution for each F number.

## Resolutions

| Item | Result | Plugin commit |
|---|---|---|
| 1 | Fixed: only the router refusing a custom load no longer means stuck | `abd0ad5` |
| 2 | Corrected, then fixed: the car makes a local move rather than stranding, and `ops_why_not` says so | `956a8b7` |
| 3 | Fixed: `first_failure` appears only when the car cannot move | `956a8b7` |
| 4 | Fixed: notes for `service_all` and same-build room, and A8 stays open when locomotives fit no change track | `956a8b7`, `9544c8b` |
| 5 | Fixed: one sample car per road, owner and build date | `edb2ae1` |
| 6 | Fixed: names the closest refusal | `708eb9d` |
| 7, 8 | Fixed | `23c3fcb` |
| 9 | Fixed | `35601e0` |
| 10 | Fixed | `8ec0aa0` |
| 11 | Corrected, then fixed: tracks do have comments in JMRI, so `add_track` and `update_track` now write them | `02ec45e` |
| 12 | Fixed | `02ec45e` |
| 13 | Fixed: the output names the train it chose and why | `956a8b7` |
| 14, 15 | Fixed | `4c410fd` |
| 16 | Fixed | `c8220ef` |
| 17 | Fixed | `23c3fcb` |
| 18 | Fixed by documenting it in SKILL.md | `e198dcb` |
| 19 | Fixed: warns from 25 backup sets and never deletes one | `e7e3a56` |
| Priority 5 docs | Fixed. `ops-diagnoser` ran in 3 of 5 fresh sessions, up from 0 of 5 | `e198dcb` |
| Test harness | Fixed. The directory log line comes from a JMRI race, so it cannot be proved gone | `40b1c9e` |

A second review after these fixes found 26 more faults. All are merged, as the commits from `c6c4e72` to `0f402a4`.

## After the reviews

The items left open were closed on 2026-11-02, and 778 tests passed on JMRI 5.16.

| Item | Result |
|---|---|
| D3 in aggressive mode | Fixed from source: stays open in a multiple pass build. Not run in a real build |
| D9 double count | Real, and fixed. A real build took a caboose under a limit that fits one |
| B19 on a rebuild | Real, and fixed. A real rebuild offered the car to its manual line again |
| `mirror_schedule` blank ship | Help text now says it takes any load of the type |
| `set_train_leg` caboose change | New `leg-caboose-stop` audit error. Real builds failed for both add and remove |
| Automation, autosave and CSV claims | Eight statements corrected against the source |
| Automation action code | Added to `file-number` |
| Empty staging mid-session | A warning when another train can refill the track, otherwise still an error |

Recorded as limits, not fixed, in the guide's Known limits:

- `ops_why_not` does not follow a load generated for a staging-to-staging move.
- A locomotive with no terminal track shows `not_checked`, though that build fails.
- Overlapping staging pool dates show `not_checked`.

# Original report

The showcase railroad was built as a test of the plugin, and no plugin code was changed while building it. Items run worst first. Paths are relative to `plugins/operations-pro` in model-railroad-skills.

## Priority 1: the tools give a wrong answer

These matter most, because a user or agent will act on the answer.

### 1. `ops_why_not` says a car can't move when JMRI moves it (F2)

- **Reproduce:** `update_stop` `SAWYER SWITCHER` stop 1 `local_moves` false, with pick ups still on. Run `ops_why_not` JFN 401 to Sawyer Pasta Plant with that train.
- **Wrong:** can_move false, first failure G3, router "could not route car". A real build still moves the car.
- **Where:** `servers/ops_gates.py:600`, the G3 gate.
- **Fix:** G3 should not need local moves on a one-stop switcher. Find the condition JMRI actually tests, then update U04 in the guide and Known limits.

### 2. `ops_why_not` says a car can move when JMRI leaves it (F3)

- **Reproduce:** `update_car` HZMX 9 passenger false, then `ops_why_not` to Turn B with `TURN`.
- **Wrong:** can_move true with no failing gate. The build log says "Leave car in staging".
- **Also:** `references/special-cars.md:73` says the car fails D4 and stays home, which is not what the run showed. Reconcile the doc with the source.
- **Fix:** add a gate for a non-passenger car returning to its starting location. Update U22 Try this.

### 3. `ops_why_not` reports first_failure on cars that do move (F2)

- **Reproduce:** the R02, R03 and R04 confirms in `GUIDE.md`. JFN 5401 to Northwood Steel with `LOCAL-H` gives can_move true and first_failure D1. R05, JFN 5501 to Linden Pier, gives first_failure D14, G8 failing and a router step saying no track found, and JMRI delivers the car.
- **Fix:** when the router finds a route, first_failure should describe the leg or be empty. The two fields should not contradict each other. Look separately at why the R05 router steps fail. Update R02 to R05 and Known limits.

### 4. `ops_why_not` ignores settings and same-build effects (F4, F5, F21)

- **service_all:** output is identical either way (R14). JFN 6402 to Linden Glazier with `EAST FREIGHT`, Linden stop `max_moves` 1.
- **E9:** passes for a spur that the same build fills first (R09: "needs 44, used 0", real build "available track space 12 feet"). At least mark E9 as open when other cars target the track.
- **A8:** passes on a copy where the build fails A8. Set Brae Engine Track `ignore_used_percent` 0, then ask about MODX 1 with `MODE` ("can depart from West Mode"). The cause is the loco change track. See `ops_gates.py:910`.

### 5. `ops_audit` false positive from its sample car (F1)

- **Reproduce:** `ops_audit` on the shipped folder gives `single-destination-schedule` on Fiddle North, Fiddle South and Grain Co Loads.
- **Cause, confirmed by running the check:** `_sample` at `servers/ops_gates.py:1767` takes the first car of the type in the file. The samples are BOXX 1 for both Fiddle schedules and JFN 101 for Grain Co Loads. Each finds no chain, while JFN 1001 and OAKX 1 do. The result depends on file order, so the warnings appear only after JMRI saves and re-sorts the cars. With no car of the type, the sample has no road and any road list refuses it.
- **Fix:** try every road that holds that type, or skip the road test for a sample. Then remove the three from `INTENDED_FINDINGS` and from the guide's Intended audit findings and Known limits.

### 6. `staging-departure-blocked` names the wrong cause (F6)

- **Reproduce:** set East Swap `ignore_used_percent` 0 in `ops_plan`.
- **Wrong:** the message says "D16 at Carrow Yard: fails E4". The real cause is A7 and D12, an occupied terminal track.
- **Fix:** follow where the car is really going, not the first stop.

## Priority 2: missing outputs, options and actions

| # | Problem | Suggested fix |
|---|---|---|
| 7 | `ops_explain_build` after `ops_dry_run` reads the old report in `buildstatus/`, with no warning (F22) | Say the report is older than the last change, or have the dry run return its own reports |
| 8 | `ops_explain_build` does not show manual build lines, only `report_text` does (F7). See U16 | Add the "Manual build line" message to the story |
| 9 | On-time abort: status Error, no report, so `ops_explain_build` has nothing (F8). `ops_build_check` and dry run are not checked for this | Report the abort from status and the log, then test those two tools |
| 10 | `ops_session update_car` is refused by audit errors and has no accept flag (F23). See R19 | Add `accept_new_errors`, as `ops_apply` has |
| 11 | `add_track` and `update_track` take no comment (F13) | Say so in `ops_actions` and refuse clearly. This may be correct, because tracks may have no comment in JMRI's data; check before adding one |
| 12 | `ops_list` tracks shows the pool name but not minimum or maximum length (F24). The XML has `minLength` and `maxLength` | Add both |
| 13 | `ops_why_not` with no train named picks one itself (F25). WNDR 1 got CUSTOM, D1 | Print which train it chose and why |

## Priority 3: discovering actions and fields

Almost every batch lost time here.

| # | Problem | Suggested fix |
|---|---|---|
| 14 | `ops_actions` gives help text but no field names (F12, F17) | Generate fields, required ones and allowed values from each action's signature |
| 15 | A wrong field leaks Python text: "set_track_moves() got an unexpected keyword argument 'track'", or "missing 1 required positional argument". Caught at `servers/ops_actions.py:417` (F12) | Turn it into a refusal that lists the valid fields |

Seen with: `comment` on tracks, `position` and `new_name` (field is `new`), `engines` (shape is `moves: {"JFN57": 200}`), `track` on `set_track_moves`, `day` on `set_active_day` (field is `name`), and `name` on `set_startup_automation` (field is `automation`). `pool` needs `{"name": ..., "min_length": ...}`, and `directions` is a numeric bitmask.

## Priority 4: noise and output size

| # | Problem | Suggested fix |
|---|---|---|
| 16 | `ops_why_not` is 15 to 20 KB per call, `ops_dry_run` about 40 KB, and `ops_list` cars prints every field of every car (F19) | A failing-gates-only option on `ops_why_not`; filters by car or track on `ops_list`; a per-car cap on the dry run summary |
| 17 | Every `ops_plan` after an `ops_apply` warns the files changed N seconds ago, though JMRI is not involved (F18). `servers/ops_store.py:212` | Skip the warning when the last change was the plugin's own apply |
| 18 | A plan that follows the skill's own start order (loads first) is blocked until `accept_new_errors` (F11). So are staging trains until cars and engines exist | Say so in SKILL.md, or treat errors that a later step of an empty railroad will clear as warnings |
| 19 | Repeated applies leave 14 or more backup sets (batch F) | Consider a retention limit. Decide whether a replay needs them |

## Priority 5: docs and agent triggering

- **`ops-diagnoser` was never chosen.** In five fresh sessions with plain questions the skill triggered every time, but the agent ran in none, even on "a long build report". Sessions used `ops_explain_build` and read the report inline. The check was too small to prove a trigger fault, so try SKILL.md directing long-report questions to the agent, then measure again.
- **`references/sessions.md`:** say a `wait_for_train_to_terminate` needs another actor. A wait on a train the same automation terminated never finishes (F9).
- **`references/staging.md`:** add that a generated load falls back to any staging track when `any_staging` is on (`setup_custom_staging` defaults it on). This is why U06's dry run does not fail (F16).
- **Schedule lines:** SKILL.md says a spur with no schedule refuses every custom load. That holds only for a car with no final destination (U03 Try this).
- **`ops_actions` and the skill:** state that a new engine model needs type and length, and that track list options are lower case (`trains`, `routes`, `excludeTrains`) (F16, F17).

## Test harness, not the shipped plugin

- `run_worker` saves when its own job ends, before a startup automation's thread finishes, so the U15 test retries up to three times (F10).
- The `terminate` job raises `KeyError` for a train built by an automation (`servers/jmri_worker.py`, the `out["builds"][train.getName()]` line in the terminate loop).
- An intermittent "Directory wasn't created" log line appears while an automation builds alongside the worker.

## Not faults, so leave these

- **Loco change moves:** an early note and F16 said a locomotive change uses two stop moves. The source review disproved it. `TrainBuilderEngines.java:876-900` touches no moves, so do not document it.
- **Name limit:** the 12-character limit is deliberate, and `set_control_limits` handles it (F14).
- **`route-stop-dead`:** correct for `max_moves` 0 (F15).
- **`place_car` on a kernel member:** the refusal is correct, but no action can then produce `kernel-split` short of `clear_kernel` (F17).
- **`add_car` and roads:** it accepts a road the track refuses, and the action text says it checks type and length only. The showcase relies on this.
- **Batch B's depots:** a build process slip, not a plugin fault (F20).

The F numbers refer to `faults.csv` beside this file. Case codes refer to `GUIDE.md`.
