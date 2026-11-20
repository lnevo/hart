# ADR-026 — AnyRail plan 5.3c is the master plan

- **Status:** Accepted
- **Date:** 2026-11-19
- **Deciders:** lnevo

## Context

The schematic's track comes from the AnyRail plan. Plan 5.3b does not match the railroad as built, so the schematic reads it with a list of overrides ([`pipelines/schematic-panels.md`](../pipelines/schematic-panels.md), layer 1): T300 moved onto the 4.25 in track, the peninsula height, crossover T41/T43 not built, and staging Switches 7, 9, 11 and 13 with EH-1 to EH-3 added.

Plan 5.3c draws these as track and joins staging to the main level through the helix ([`STATUS.md`](../STATUS.md), "AnyRail plan 5.3c").

## Decision

`Lee Nevo Design Version 5.3c.any` in `~/Documents/Layout/` is the master copy of the layout plan (owner, 2026-11-19).

**Taken from 5.3c today**
- The engine house track lengths, EH-1 49 in and EH-2 and EH-3 28 in each: the drawn length rounded down, less 2 in ([`docs/jmri/TRACK_LENGTHS.md`](../../docs/jmri/TRACK_LENGTHS.md)).
- The helix lengths in `helix_length_in`, which moved the milepost-named intermediate masts to A83/A84 and B92/B93 (PR #689, ADR-024).

**Still from 5.3b**
- The schematic inputs in `jmri/layouts/hart/data/schematic/inputs/` are read from AnyRail's JMRI export of plan 5.3b, with the overrides. They stay so until 5.3c is brought in. That has not happened.
- The inferred block lengths in `TRACK_LENGTHS.md` are timed shares of the 5.3b loop.
- The track plan page on the website is drawn from 5.3b (`tools/anyrail/levels_page.py`).

**The reader**
- `tools/anyrail/anyplan.py` reads a plan from the `.any` file itself, for any maker's track, and finds records by their shape instead of per-file tags or part names (PR #692, merged 2026-11-19). It reads 5.3b with the same switch-to-switch runs as AnyRail's export. It is not yet the source of the schematic inputs.

## Consequences

- Until the bring-in, a fact that differs between the two plans is taken from 5.3c by hand and noted with its source, as the engine house and helix lengths are.
- The bring-in changes the schematic inputs. The approved fingerprints (`check_approved.py`) stop a panel or desk that changes with them until the owner approves it.
- The `.any` file and its export stay in `~/Documents/Layout/`, outside the repo.

## Open

- The bring-in of 5.3c as the schematic source has no date and no written plan in the repo.
- Which of the 5.3b overrides remain after the bring-in is not recorded.
