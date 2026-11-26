# ADR-026 — AnyRail plan 5.3c is the master plan

- **Status:** Accepted
- **Date:** 2026-11-19
- **Deciders:** lnevo

## Context

The schematic's track comes from the AnyRail plan. Plan 5.3b does not match the railroad as built, so the schematic reads it with a list of overrides ([`pipelines/schematic-panels.md`](../pipelines/schematic-panels.md), layer 1): T300 moved onto the 4.25 in track, the peninsula height, crossover T41/T43 not built, and staging Switches 7, 9, 11 and 13 with EH-1 to EH-3 added.

Plan 5.3c draws these as track and joins staging to the main level through the helix ([status entry](../status/current/anyrail-plan-5-3c.md), "AnyRail plan 5.3c").

## Decision

`Lee Nevo Design Version 5.3c.any` in `~/Documents/Layout/` is the master copy of the layout plan (owner, 2026-11-19).

**Taken from 5.3c by hand**
- The engine house track lengths, EH-1 49 in and EH-2 and EH-3 28 in each: the drawn length rounded down, less 2 in. Superseded on 2026-11-20 (below): they are the plain 5.3c lengths now.
- The helix lengths in `helix_length_in`, which moved the milepost-named intermediate masts to A83/A84 and B92/B93 (PR #689, ADR-024).
- Phase 2 (2026-11-19) took the rest: the inputs, the helix (each level's share up to the -5 cm cut, `anyplan.py --cut -5 --stubs`, replacing `helix_length_in` with the same totals, so the masts kept their names) and the drop of the overrides 5.3c draws as track.

**The schematic**
- The schematic inputs in `jmri/layouts/hart/data/schematic/inputs/` come from 5.3c, read by the schematic-maps plugin's `schematic anyplan` (hart's own `tools/anyrail/anyplan.py` until 2026-11-21), and the overrides 5.3c draws as track are dropped. The bring-in steps are in [`archive/history/wiki/projects/anyrail-5-3c-handoff.md`](../../archive/history/wiki/projects/anyrail-5-3c-handoff.md).
- `anyplan.py` reads a plan from the `.any` file itself, for any maker's track, and finds records by their shape instead of per-file tags or part names (PR #692). The same reader ships in the schematic-maps plugin since 0.1.51 (model-railroad-skills#84), and hart uses it there (2026-11-21).

**Block lengths (owner, 2026-11-20)**
- Every staging block has its 5.3c length in `block_lengths.csv` (`plan_in`), written by `tools/schematic/plan_lengths.py` from the plan file and `parts.json`: a track block the plan's run between the turnout ends (as AnyRail's export measures it), an OS block its turnout's product length from the points to the frog end, read from the part's end points (a Peco code 83 #6 about 9.2 in, a #8 11.1 in). No hand-kept lengths are left: the old layout's yard and spur lengths, the 10 in OS placeholders and the engine house rule above are gone.
- The schematic, the Layout Editor panel and the signal rules use the plan length alone, so masts stand where the rules put them on the plan's geometry. Car counts and mileposts use the plugin's plan lengths on every level; staging's copy of the measured lengths in `staging.plan_overrides.json` (`track_lengths_in`) is gone.
- A timed block keeps its measured length (`measured_in`, `source` `timed`) for speed profiling and for JMRI's block length; JMRI holds the measured length where there is one, else the plan length (`export_track_lengths.py --tables` writes them, `--check` holds `tables.xml` to the file).

**Still from 5.3b**
- The measured block lengths (`source` `timed` in `TRACK_LENGTHS.md`) are timed shares of the 5.3b loop. `infer_block_lengths.py` now reads its loop values from the 5.3c plan (`plan_routes.py`), so the next re-measure gives 5.3c shares.
- The track plan page on the website is drawn from 5.3b (`tools/anyrail/levels_page.py`).

## Consequences

- A fact that differs between the two plans is taken from 5.3c and noted with its source, as the engine house and helix lengths are.
- Bringing 5.3c in changes the schematic inputs. The approved fingerprints (`check_approved.py`) stop a panel or desk that changes with them until the owner approves it.
- The `.any` file and its export stay in `~/Documents/Layout/`, outside the repo.

## Open

- The bring-in is built (Phase 2, 2026-11-19) and waits for the owner's approval of the panel and desks.
- The measured block lengths and the website's track plan page have no plan to move to 5.3c.
