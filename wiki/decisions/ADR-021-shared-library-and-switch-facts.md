# ADR-021 — Shared library and switch facts

- **Status:** Accepted
- **Date:** 2026-11-13
- **Deciders:** lnevo

## Context

An architecture review on 2026-11-12, before the two remaining levels are imported, found two problems that grow with the layout:

- **The same fact in several places.** "Switch 9 normal leads to EH-2" lived in `tables.xml`, the CATS Designer save, constants in `wire_digicon.py` and `gen_ctc_track_plan.py`, and the name map. The Switch 9 rewiring took three commits to bring them back into agreement, and the USS board stayed stale until a check found it.
- **The same code in many places.** About 70 CPython scripts parsed `tables.xml` on their own and about 70 changed `sys.path` to reach each other. `JMRI_LAYOUT` suggested several layouts, but scripts hard-coded `layouts/hart`.

## Decision

1. **Switch facts live in data.** `jmri/layouts/hart/data/switches.csv` (level, number, Layout Editor turnout, CATS inversion, USS lever) and `switch_legs.csv` (closed and thrown leg per OS block) hold them; hardware and DCC addresses stay in `public_name_map.csv`. `wire_digicon.py` and `gen_ctc_track_plan.py` read them. `tools/audit/check_layout_facts.py` (in `tools/check.sh`) checks the Layout Editor, both CATS desks and the USS board against them. Switch plate numbers are unique across the railroad. How to change a switch: [`pipelines/switch-facts.md`](../pipelines/switch-facts.md).
2. **CPython tools use `hartlib`** (`tools/hartlib/`): `paths` (this checkout's files), `tables` (load and save `tables.xml` byte-for-byte as JMRI writes it, plus lookups) and `hosts` (broker and host settings). New and changed scripts start with its two bootstrap lines; [`tools/hartlib/README.md`](../../tools/hartlib/README.md) has the API, the `tables.xml` traps and the steps for moving a script. Jython scripts that run inside JMRI never import it.
3. **One layout.** `hartlib.paths.LAYOUT` is pinned to `hart` and `load_env.sh` replaces any other `JMRI_LAYOUT`. When the railroad is split for the new levels, the unit is the level or district (the `level` column), not a layout name.
4. **Deploy lives in `tools/hosts/`** with one host configuration shared by shell and Python, and stamps what it shipped on each host (ADR-007 amendment 2026-11-12).

## Consequences

- A rewiring is a data change plus the generators, and a disagreement fails `check.sh` with the switch and both sources named.
- `tables.xml` knowledge (duplicate sections, doubled blocks, virtual masts, JDOM escapes) is in one module; a writer's `save()` refuses while PanelPro or CATS is open, and the repo hook spots hartlib writers by import.
- Adding a level needs a USS board design decision; the data and checks already carry `level`.
- Dispatcher stations for the new levels are defined in PanelPro once the upper level is done. The stale `add_yard_ladder_le_icons.py` ship entry was removed 2026-11-13 (PR #394); a copy already on the hosts is inert.

## Amendment 2026-11-14: one fact, one place, past the switches

A re-review before the main and upper levels found the rule stopped at switches: level was one column, Switch 9's hand sat in a drawing script, the DCC address was read out of free-text comments, mast cells were listed in both CATS and USS generators, and a single mast rename touched about 13 files. The owner approved preparing the data model now; the level import itself waits for an ADR once the upper level is drawn.

1. **Level per control point.** `control_points.csv` has a `level` column (and an Engine House row for Switches 9, 11 and 13, whose turnout rows now carry that `cp`). Masts, heads, blocks and sensors take their level from their `cp`, OS blocks and switch legs from their switch, mains between control points from the blocks they join (`layout_facts.name_map_levels`, held by `check_layout_facts.py`). No grouping above the control point exists, so there is no district column yet.
2. **Hand per switch.** `switches.csv` has `hand` (L, R or blank). Only Switch 9 (L) is recorded; the Layout Editor's RH/LH types are not a source (it still draws Switch 9 right hand).
3. **DCC address in its own column** of `public_name_map.csv`. `hartlib.names` is the one DCC grammar: it puts the address back as the comment's second group, so JMRI comments are unchanged, and refuses a comment it cannot round-trip exactly.
4. **One mast-cell table.** `mast_cells.csv` holds each mast's CATS desk cell and USS icon, read by `wire_digicon.py` and `gen_ctc_track_plan.py`. `cats/data/turnout_bindings.csv` is gone: the CATS turnout bindings come from `switches.csv`.
5. **Derived files fail when stale.** `www/data/layout-index.json` and `layout-index-cats.json` have a `--check` in `check.sh` that also covers their PNGs through a recorded hash of the render inputs, beside the baselines and tables browser already there. `staging.signals.json` (needs the plan graph outside the repo) and the hand-kept `www/review-data/hart_devices_review.json` are not checked.

Generator outputs (both CATS desks, the USS panel and `GUIObjects.xml`, the `tables.xml` comment pass, the name map rebuild, the engine terminal drawing) were byte-identical before and after. The website indexes changed only by the new hash and Switch 9 and 11's control point; their PNGs were re-rendered, as they had not been since the 16R rename. How to change a mast, track or level: [`pipelines/switch-facts.md`](../pipelines/switch-facts.md).
