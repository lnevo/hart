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
order.

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

## What is left to remove, ranked

| # | Item | Where | Replace with | Effort |
|---|---|---|---|---|
| 1 | Plan part numbers (T-numbers) as keys: about 101 across four files, re-matched by position on every export | `staging` and `main_upper` `.plan_overrides.json` (`name`, `end`, `helix`) and `.preferences.json` (`min_cells`, `shorten`, `edits` flip, `levels.assign`, `level_leg`) | Switch number and leg keys (the `1B-3A` form `staging_device_map` already uses). The relabel map stays plan-keyed: it is the link from plan to owner numbers. The plugin's `edits` must accept label keys | 1–2 days |
| 2 | Dead or stale entries | `mast_dir_pattern` and `signals_planned` in both override files (only the plugin's `signals` command reads them); the T300 `move` hand branch in `build_hands.py`; comments that still name helix Switches 129/135; the hartlib `railroad.py` docstring calling `staging_masts.csv` hand-kept | Delete or correct | under an hour |
| 3 | Mast direction read from the name: "L is west", and the odd/even number for intermediates | `build_cats_panel.py`, `build_main_upper_masts.py`, `build_signals.py` | A `dir` column in the mast data, read where needed | half a day |
| 4 | Station and control-point membership kept in up to four places; the staging main line marked by hand (a `main` flag on 8 tracks, a 7-hop `milepost_route`) | `staging.plan_overrides.json`, `control_points_staging.csv`, `interlockings_staging.csv`, `detail_sheets`, the old `control_points.csv` | One source with the rest generated; a staging main-lines file through `build_main_route.py` | 1 day |
| 5 | Hand lists keyed by generated track names, which break when names are renumbered | `running_tracks_main_upper.csv`, `signalled_spurs_main_upper.csv`, `split_tracks_main_upper.csv`, the `block` columns of the detector pins and helix files, `le_band_labels` | Key by end-switch pair | half a day to a day |
| 6 | **Track-plan page, regenerate from 5.3c (owner).** `tools/anyrail/staging_plan.svg` has no generator; the page text and `levels_svg.py` are built around the 5.3b corrections (T300 move, T41/T43, typed numbers) | `tools/anyrail/`, `www/build/track-plan.html` | Draw the staging plan from the 5.3c export; compute the page's numbers from data; drop the 5.3b correction overlay | half a day to a day |
| 7 | Peco product table in `plan_lengths.py`, against the "any maker" rule | `tools/schematic/plan_lengths.py` (`PRODUCTS`) | Turnout length from the part's geometry; keep the table only as a sanity range | a couple of hours |
| 8 | Kind and level read from name prefixes ("Track ", "OS Switch ", "BS ", "Mast "), the crossover half from A or B, a balloon loop from a name ending " Loop", the level from a band title's first word | hartlib (`level_devices`, `railroad`), `le_names`, `staging_device_map`, `build_device_map`, `build_cats_panel`, `mast_rule` | `kind`, `level` and `role` columns on the device-map rows | several small steps |
| 9 | Device facts kept three times (addresses, DCC, node comments in `public_name_map.csv`, `device_map_staging.csv` and `tables.xml`); the DCC group parsed from `tables.xml` comments; build-owned items found by comment and name | hartlib `names.py`, `le_tables.py` | One master with the others generated; an explicit owner column | 1–2 days |
| 10 | Drawing workarounds in preferences | `level_leg`, `le_tight_crossovers`/`le_split_crossovers` (101/103), `le_shift`, `le_labels` groupings | Plugin rules (for example: choose the level leg when the straight-level rule would collide) | 1–2 days |

Also open, smaller:
- whether `le_signal_boundaries.csv` is still needed now that staging masts come from the rule;
- the owner's screen sizes (`le_window`, `cats_window`) sitting in preferences;
- the band names and the 5 cm cut kept in `main_upper.plan_overrides.json` `levels` "until B2";
- the website's repository guide and JMRI additions page, out of date since 2026-11-18 (they call `staging_masts.csv` hand-kept).

## Not checked by the audit

- the plugin's label, band and CATS internals beyond its signal reader and mileposts;
- some function bodies (`build_layout_le.py`, `le_tables.py`, `le_checks.py`, `publish_draft.py`, `panel_items.py`);
- the scripts that run inside JMRI;
- the parked folder.

## How to take it on

1. The owner reviews the table and orders it.
2. One PR per row, each through `make panels`, `./tools/check.sh` and, where the panel changes, one owner approval.
3. Rows 2, 3 and 7 change no drawing and can go together.
4. Row 1 should come before the next AnyRail export.
