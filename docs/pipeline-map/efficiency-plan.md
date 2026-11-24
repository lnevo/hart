# Pipeline efficiency plan (2026-11-21)

Plan to cut panel rebuilds and full workflow runs, based on logged step timings, reviewed by the owner on 2026-11-21.

This plan works through what the pipeline map shows. The goal is fewer panel rebuilds and fewer full workflow runs. The owner reviewed every topic on 2026-11-21. The plan runs alongside the ADR-030 work and waits for it where the two touch the same files.

## What the timings show

Logged `make panels` steps (149 runs): schematic 21 s average, Layout Editor cut-over 14 s, device map 3 s, CATS 2 s, the rest under 1 s, so a full rebuild takes about 40 s. A full `check.sh` takes 2 to 5 min, SML discovery about 3 min in PanelPro, and `panelpro-test` 2 to 3 min. The hours come from repeated loops, not from the steps: a stale input or a by-hand step found after a rebuild, a check and an approval, then a Store split and another rebuild. The plan cuts the loops.

Heavy checks run on the Windows box (`make remote`). `panelpro-test`, SML discovery and deploys stay on the Mac. Layout changes must come out byte-identical (`tables.xml`, desks, Layout Editor panel, approved fingerprints), so they need no new approvals.

## Topics

| Topic | What | Weight | State |
|---|---|---|---|
| T1 | Outputs the map showed with no reader: 12 were missing links, 8 are end products, 2 were wrongly labelled as outputs | S | Done (#853) |
| T2 | Two writers drawn for one output: map errors and different jobs, no real duplicate code | S | Done (#853) |
| T3 | Move the generated `signal_head_plan.csv` from `docs/` to `jmri/layouts/hart/output/` (host path unchanged) | S–M | Done (#867) |
| T4 | Input stamps on the by-hand steps: `make panels` stops in under a second when SML discovery is stale, and runs the mast builder itself | M | Done (#867; SML guard topology-only #897) |
| T5 | Skip `make panels` steps whose inputs did not change (same stamps as T4) | S | Done (#867) |
| T6a | Device master as two files: `devices_generated.csv` (scripts) and `devices_field.csv` (the owner's cells and Store-added devices), merged by `hartlib.devices` ([ADR-029 amendment](../../wiki/decisions/ADR-029-tables-xml-is-an-output.md)). Step 0 routes every reader through `hartlib.devices` | L | Done (#869, #890) |
| T6b | Generated sections of `plan_overrides.json` move to `plan_generated.json` | M | Done (#901) |
| T7 | Wiring one way: unfrozen wiring is a proposal in the generated rows; `make wiring-freeze` is the only writer into `wiring.csv` | M | Done (#900) |
| T8a | Site build in stages; the photo stages are reused when their inputs are unchanged (build 7.8 s to 2.9 s) | M | Done (#854 tests, #861) |
| T8b | Deploy as gate, stage, then ship per host, so every check runs before anything ships (#855 tests found four gates that run after shipping starts) | M–L | Done (#855, #873) |
| T9a | The deploy keeps a changed Pi Store or Operations session in the pull folder and stops | M | Done (#887) |
| T9b | `tools/schematic/template_edit.py`: memories, clock and settings without a Store | M | Done (#862) |
| T10a | `bin/cars compare` checks the STS seed copies; `bin/cars seed-copy` refreshes them | S | Done (#852) |
| T10b | `bin/cars compare` field differences against Operations Pro and the STS seed | S–M | Done (#860) |
| T10c | `bin/cars sync` sends corrected fields of existing cars, dry run and backup first | M | Done (#871); the first live `--apply` needs the owner's yes |

Also done on 2026-11-21: the schematic film is built by `evolution.py --site` (#857), and every panel film runs at one pace, 0.4 s a frame with a 2 s final hold (`hartlib.film_pace`, #858).

## Order

T3, T4, T5, T8b and T9a are done (2026-11-21). Still to do, in this order because they touch the same files: the T6a split (step 0 is done, #869), T6b, then T7. Then one `panelpro-test`, a deploy if a shipped file changed, and one pipeline map update for everything above.

## Result (2026-11-21)

Every topic is merged and deployed (Pi and Windows from 1bc9cab8, website the same day). Also done that day: the panel films at one pace (#857, #858), check.sh job stamps (#880), the caches and pulled Stores inside the repo (#876), `make remote` limited to two runs on the Windows box (#892), and the pipeline map brought up to date (#902). Layout outputs stayed byte-identical throughout, so no panel approvals were needed.

Timings now: a warm `make panels` 4–6 s (was about 45 s), a warm local `check.sh` about 40 s (was 2–5 min), a text-only site build 3 s (was 8 s), a `--pi --win` deploy about 35 s with every check before anything ships.

## Full rebuild timed (2026-11-23)

The owner chose a full rebuild as the timed run in place of a real edit (2026-11-22). Both runs on the Mac, plugin b0bc62ee, each with a new empty plugin cache (`SCHEMATIC_CACHE`), so nothing was read back.

**As approved** (`make panels FULL=1` on main c44a00db): 431 s, every step passed.

| Step | Time |
|---|---|
| plan-lengths (reads the AnyRail plan) | 37 s |
| schematic (the solve, sheet and station pages) | 38 s |
| sml-current (builds `tables.xml` in memory, the Layout Editor panel first) | 343 s |
| cats | 4 s |
| tables (reads the panel back from the cache) | 2 s |
| the other eleven steps | 7 s together |

The cold Layout Editor build is 80% of the run. The 40 s full rebuild in "What the timings show" and the warm 4–6 s above both had a warm cache.

**Raw, from the plugin alone:** the plugin's own commands with `--no-preferences` on the same plan graphs, plan facts and signals (no band order, width, alignment or shift, no `level_leg` pins, no turnbacks, no Layout Editor or CATS tuning):

| Command | Time | Result |
|---|---|---|
| `draw` (the solve, cold) | 38 s | 3 bands, 0 crossings or overlaps, 0 label faults; the main slopes at 4 switches (33, 109, 219, 229) |
| `report` | 0.2 s | as above |
| `le` at the plugin's grid | 1.5 s | 61 turnouts, 216 track segments, 187 blocks; 2370 x 1236 px, wider than the hosts' 1920 x 1032 window |
| `le --fit 1920x1032` | 17.7 s | stopped: 20 block contents labels found no clean spot on the shrunk grid |
| `cats --window 1920x1032` | 0.2 s | 0 desk faults; 116 x 57 cells, so CATS scrolls |

So the solve costs the same either way (38 s); the preferences' Layout Editor passes cost about 5.5 minutes on a cold cache. The HART builders cannot run without the preferences: with `preferences.json` cut to `host_screen`, `build_device_map.py` stops (a band with no `rail`) and the `plan-lengths` guard stops on new track names (1A-23A, 1C-5A). The raw files were put in `~/JMRI_UserFiles/raw-experiment/` on the Mac for the owner to look at; nothing was deployed.

**One railroad, one band (owner, 2026-11-23):** the raw run above still drew three bands, because the cut into levels is in layer 1 (`levels`, `helix`) and staging is its own input. As an experiment, staging's and main's plan graphs were joined into one, the two helix cuts spliced (39 to 131A as Helix Outer, 37 to 131B as Helix Inner), and the plugin given one input with the switch numbers, track names and signals but no `levels`, `helix` or helix ends. The plugin's facing search allows at most 5 turnbacks on a plan this big and found none; with the cap raised to 7 from a wrapper (plugin files unchanged) it found an orientation in 37 s with 6 turnbacks: staging 23-1 and 39-37, the main's 107 loop, upper 241-227 and the two runs between 211 and 217. The row search then ran 43 minutes and the column placement stopped (`columns: constraints do not settle`), so no drawing came out; a sketch of the facing, columns and sweep order was shown instead. The plugin does not yet lay out the whole railroad as one band.

## Cold Layout Editor build profiled (2026-11-24)

`python3 -m cProfile` on `check_sml_current.py` (it builds `tables.xml` in memory, the Layout Editor panel first) with `SCHEMATIC_CACHE=` empty, plugin 19261998, main 33abbf05: 957 s under the profiler (the 431 s run above is the same work without it). Shares of the run:

| Pass | Share | Where |
|---|---|---|
| Label placement | 71% | `le_labels.place`: 130,000 `take` calls try about 180 spots each, so 23 million `fault` checks; inside them about 190 million segment tests (`within`, `touches`) and 250 million grid lookups (`Grid.near`) |
| The sheet solve | 24% | `sheet.solve` (`layout.settle`, `rows.optimise`) |
| The device map's solve | 16% | `build_device_map.solve` through `le_names.placeholder_names`; overlaps the row above |

`settle_gaps` (`le.py`) draws the panel twice, the first time at the default gaps between bands and again at the gaps that drawing asks for. Each drawing runs the whole label placement, so half of the 71% is the first drawing.

Proposed cuts, each one byte-identical because the drawing that is kept does not change. They are plugin changes (`external/model-railroad-skills`) and are not built yet:

1. **Start `settle_gaps` from the last settled gaps.** Keep `P.gaps` with the panel's inputs and try them first. The loop already accepts a guess only when the drawing asks for exactly those gaps, so a right guess draws once and a wrong one costs what it does now. Saves about half of the label placement.
2. **Remember the fixed part of `fault`.** Track lines, turnout circles, the panel edge and `reads_other` do not change while labels are placed; only the placed boxes do. Cache that verdict per (item, spot, on) for the whole placement, and check the placed boxes live as now. The same spots come up again across the 797 placement attempts, so this removes most of the 190 million segment tests.
3. **One solve per sheet in a run.** With the cache off, the device map solves the same sheets a second time. A real cold run has the cache on but empty, so its memo may already share them: check before building anything.

Do 1 and 2 before the next plugin pin bump, which empties the cache.

## Measure a real edit (replaced by the full rebuild above)


The speed-ups above are measured on repeat runs. The plan's real aim, fewer round trips on a layout change, has not been timed yet. On the next real change (a block split, a Store split, a mast or a wiring change; owner, 2026-11-21):

1. Start `make mqtt-watch` (the `_discard` watcher, read-only) on the Mac before the first edit and leave it running until the deploy is done; note any `NEW` line.
2. Log the time (`date +%H:%M`) at each step: first edit, each `make panels` (with its time and how many steps ran or skipped), each `check.sh` and CI run, each owner approval, any Store pull or split, any SML discovery on the Mac, the deploy.
3. Count the round trips: how many rebuilds, checks and approvals the change took, and why each extra one happened.
4. Put the result in this section, with the date, as the "after" figure for the plan.

