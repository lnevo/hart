# Hand-off, 2026-11-19: bring the AnyRail plan 5.3c in (Phase 2)

For a fresh agent session. Read `AGENTS.md`, then this page, then
[`pipelines/schematic-panels.md`](../pipelines/schematic-panels.md) and
[ADR-024](../decisions/ADR-024-signals-by-rule.md).

## Why

The owner made `~/Documents/Layout/Lee Nevo Design Version 5.3c.any` the good copy of the layout
(2026-11-19). The schematic inputs still come from the 5.3b export plus overrides. 5.3c draws
what those overrides describe, and it renumbers every T name.

The plan files stay private in `~/Documents/Layout` and are never committed: the custom objects
in them are third-party copyright.

## State when this was written

- **Export ready:** `Lee Nevo Design Version 5.3c.xml` and `.jpg`, saved 16:17 on 2026-11-19,
  a minute after the `.any`. The image is 2664×3840 (about 12.0 px/in); the XML holds 74
  turnouts and 539 track segments.
- **Phase 1 is merged** (hart #692): `tools/anyrail/anyplan.py` reads any maker's `.any`
  (`--report`, `--parts`); its tests run on the owner's plans when they are present.
- **5.3c checks out:** one connected piece, every turnout level, no near misses, a maximum
  grade of 2.25%. The helix runs are Switch 39 to 135A, 947.19 in, and Switch 37 to 135B,
  916.50 in.
- **Already taken from 5.3c** (hart #689): the engine house lengths EH-1 49, EH-2 28 and
  EH-3 28 in (drawn length rounded down, less 2 in; flag `plan` in `block_lengths.csv`), and the
  helix lengths in `staging.plan_overrides.json` `helix_length_in`.
- **Plugin scale fix:** model-railroad-skills PR #74 (branch `agent/claude/plan-scale`,
  schematic-maps 0.1.44) has unmerged commits. Its lengths use the export's fitted scale instead of
  a fixed 12 px/in, a change of 0.1–0.4%. It sits on hart-e5's crossover changes (0.1.42 and
  0.1.43) and waits to be merged with this phase.
- **Mast B93** lacks the intermediateSignal flag. That is correct stock behaviour: its route
  crosses Switch 239 (ADR-024).

## Blocked on

hart #693 (hart-e5's crossover renumber, "E") must merge first, after the owner approves it. It
renames switches that this phase re-keys. If the plugin's main moves again, merge it into #74
and take the next version number (both `plugin.json` files and the README "Since 0.1.4x" note).

## Steps

1. Make `jmri/layouts/hart/data/schematic/inputs/parts.json` from
   `python3 tools/anyrail/anyplan.py --parts` on the 5.3c `.any`. Map the old T names to the new
   ones by position.
2. Merge plugin #74 and move the submodule to it.
3. Take the helix from the plan: the levels meet at the −5 cm cut. Remove `helix_length_in` and
   the 24 in McKees Rocks and McKeesport stub estimates from `staging.plan_overrides.json`. The
   owner wants these lengths from AnyRail, not measured.
4. Drop the overrides 5.3c now covers in `staging.plan_overrides.json` and
   `main_upper.plan_overrides.json`.
5. Re-key the edge and node ids in `split_tracks_main_upper.csv`, `staging_signals.csv`,
   `staging_signals_virtual.csv` and `device_map_staging.csv`.
6. Fix the "planned ?" head comments: `tools/schematic/le_tables.py` writes
   `device.get(h, '?')` after `SIGNAL_NOTE`.
7. Run `make panels`, stock Signal Mast Logic discovery in a sandbox, `./tools/check.sh` and
   `make panelpro-test`. The milepost-named masts (A83/A84, B92/B93) will probably rename;
   update ADR-024 and STATUS when they do.
8. Install the candidate `tables.xml` in `~/JMRI_UserFiles`, relaunch the Mac's PanelPro, and ask
   the owner for one approval of the panel and desks. Then refresh the fingerprints with
   `check_approved.py --approve`.
9. Deploy to the Pi and Windows together (`./tools/hosts/sync_hart_package.sh --pi --win`).

## Also open

The Windows deploy of hart #689 has not run, because Windows (minipc-e5h6x.local, 10.0.0.28:2222)
was unreachable. The Pi has that commit. The deploy in step 9 catches Windows up; if Windows comes
back sooner, run `--win` alone from the main checkout.
