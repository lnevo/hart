# Hand-off, 2026-11-20: what still builds the layout besides the plan and structured data

For a fresh agent session. Read `AGENTS.md`, then this page, then
[`pipelines/schematic-panels.md`](../pipelines/schematic-panels.md).

## Why

The owner's goal (2026-11-20): the AnyRail plan 5.3c and structured data build the layout. Exceptions, one-offs
and rules read from names or free text should go. The 5.3c clean-up branch (`agent/claude/plan-5-3c-cleanup`) moved
these to plan or data:
- lengths;
- the helix blocks;
- the hidden staging masts;
- the yard throats;
- the device-map facts;
- the main/upper main route;
- the block numbering;
- the 35-37 short track.

A read-only audit of that branch then listed what is left. This page is that list, for the owner to review and
order; rows 1 to 7 are done.

**Owner decision (2026-11-20): the track-plan page is regenerated from 5.3c (item 6), not retired.**

## What stays: railroad facts the plan cannot hold

- **Wiring and addresses:**
  - the device maps;
  - `lcos_nodes_main_upper.csv`;
  - `detector_pins_main_upper.csv`;
  - `switches.csv` and `switch_legs.csv`;
  - `public_name_map.csv`.
- **The owner's choices:**
  - switch numbers (the relabel maps);
  - control points and stations;
  - `block_numbering.csv`;
  - `helix_tracks.csv`;
  - `short_tracks_staging.csv`;
  - `main_lines_main_upper.csv`;
  - the milepost origin (Switch 1 is MP 5.7).
- **Measured facts:**
  - the timed lengths (`block_lengths.csv` `measured_in`);
  - the physical hands of Switches 9 and 13.

## Progress (2026-11-20)

Done on branch `agent/claude/source-data-rows-2-3-7`, with every desk, panel and fingerprint unchanged:
- **Row 1:** every override and preference ref outside the `relabel` edit is a switch number, or `number@track` at
  a crossover half (about 95 refs). Six stayed part numbers: the first track named at each half of Switches 7, 23
  and 35 in the staging `name` edit, since no track had a name yet for `@track` to use.
- **Row 2:** `mast_dir_pattern` and `signals_planned` deleted, the `move` hand branch gone from `build_hands.py`,
  comments corrected (127 and 131 at the helix top since the 2026-11-19 renumber).
- **Row 3:** a mast's direction is the `dir` column (east or west) of the device maps, `main_upper_masts.csv` and
  `staging_masts.csv`, set where the mast rule places it; no reader parses it from the name.
- **Row 7:** a turnout's class (#6 or #8) comes from the angle of its leg ends; the Peco part table is gone.

Merged as #754. Then, on branch `agent/claude/source-data-rows-4-5`, also with nothing drawn changed:
- **Row 4:** staging's control points (`control_points_staging.csv`), stations (`stations_staging.csv`), detail
  sheets (`sheets_staging.csv`) and main lines (`main_lines_staging.csv`) each have one master file;
  `build_staging_sets.py` and `build_main_route.py` write every other copy, the older `data/control_points.csv`
  included (the website build and the JMRI scripts still read it), and `make panels CHECK=1` fails on drift.
- **Row 5:** the main/upper hand lists (running, signalled spurs, split tracks, detector pins) are keyed by
  `switch_a,switch_b` (and `parallel` or `half` where needed), so a renumber no longer strands them. The
  `le_band_labels` names in `main_upper.preferences.json` stay track and block names (owner, 2026-11-20): a main or
  upper name is built from its end switches, so a renumber changes a switch pair just as it changes the name, and a
  stale name already stops the build (`hidden_names`) or leaves an icon unplaced, which fails the label check.

Then, on branch `agent/claude/label-refs-by-switch` (schematic-maps 0.1.47), with nothing drawn changed: those six
reach their half as `number@neighbour` (`23@1`: the half a track joins to Switch 1), so no part number is left
outside the `relabel` edit; `test_override_refs.py` checks each finds the half its part number did.

Row 6 (track-plan page, regenerated from 5.3c: `levels_svg.py` draws all three levels from the `.any` through `anyplan.py`) is merged from another session (#749). Rows 8, 9 and 10 wait (owner, 2026-11-20).

## What is left to remove, ranked

Rows 1 to 7 are done (#749, #754, #757 and the label-refs branch, above); the table keeps the open rows with their original numbers.

| # | Item | Where | Replace with | Effort |
|---|---|---|---|---|
| 8 | Kind and level read from name prefixes ("Track ", "OS Switch ", "BS ", "Mast "), the crossover half from A or B, a balloon loop from a name ending " Loop", the level from a band title's first word | hartlib (`level_devices`, `railroad`), `le_names`, `staging_device_map`, `build_device_map`, `build_cats_panel`, `mast_rule` | `kind`, `level` and `role` columns on the device-map rows | several small steps |
| 9 | Device facts kept three times (addresses, DCC, node comments in `public_name_map.csv`, `device_map_staging.csv` and `tables.xml`); the DCC group parsed from `tables.xml` comments; build-owned items found by comment and name | hartlib `names.py`, `le_tables.py` | One master with the others generated; an explicit owner column | 1–2 days |
| 10 | Drawing workarounds in preferences | `level_leg`, `le_tight_crossovers`/`le_split_crossovers` (101/103), `le_shift`, `le_labels` groupings | Plugin rules (for example: choose the level leg when the straight-level rule would collide) | 1–2 days |

Also open, smaller:
- whether `le_signal_boundaries.csv` is still needed now that staging masts come from the rule;
- the owner's screen sizes (`le_window`, `cats_window`) sitting in preferences;
- the band names and the 5 cm cut kept in `main_upper.plan_overrides.json` `levels` "until B2";

## Not checked by the audit

- the plugin's label, band and CATS internals beyond its signal reader and mileposts;
- some function bodies (`build_layout_le.py`, `le_tables.py`, `le_checks.py`, `publish_draft.py`, `panel_items.py`);
- the scripts that run inside JMRI;
- the parked folder.

## How to take it on

1. The owner reviews the table and orders it.
2. One PR per row, each through `make panels`, `./tools/check.sh` and, where the panel changes, one owner approval.
