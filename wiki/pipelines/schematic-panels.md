# Pipeline 19 — Panels from the schematic

Every panel is drawn from the approved schematic: the switch hands, the signal plan, the device map for the main and
upper levels, the published schematic and station sheets, the CATS desks and the Layout Editor panel (built as
a candidate beside `tables.xml`). The schematic-maps plugin (`external/model-railroad-skills`) solves the sheet; the scripts in
`tools/schematic/` turn it into each output. This replaced the AnyRail pipeline ([jmri-anyrail.md](jmri-anyrail.md)).

**Status:** Live. The Layout Editor cut-over (2026-11-16) and the CATS desks (ADR-023) are built this way.

## Run

```bash
make panels           # rebuild every output, in order; stops at the first failure
make panels CHECK=1   # check every output; names each stale one
make desks            # only the CATS desks, then validate them
```

`tools/schematic/build_panels.sh` runs the steps in the order they depend on each other:

| Step | Script | Writes |
|------|--------|--------|
| hands | `build_hands.py` | `hands.csv` from the plan graph |
| staging-map | `staging_device_map.py` | staging's facts in the device map's form (`device_map_staging.csv`, `control_points_staging.csv`, `staging_masts.csv`, `staging_signals.csv`), converted from the frozen `staging_le/` files until staging switches to the device-map path |
| signals | `build_signals.py` | `<name>.signals.json` from the plan graph and the staging masts (`staging_signals.csv`, `staging_masts.csv`) |
| device-map | `build_device_map.py` | `device_map_main_upper.csv` and the layer overrides the schematic reads |
| main-upper-masts | `build_main_upper_masts.py` | `main_upper_masts.csv` for the Layout Editor builds |
| schematic | `publish_draft.py` | the schematic sheets and station pages |
| cats | `build_cats_panel.py` | `cats/panels/HART_CTC.xml`, `HART_ABS.xml` and `HART_CTC.bindings.json` |
| le-trial, le-trial-staging | `build_layout_le.py` | Layout Editor trial panels (all levels, then staging alone) |
| le-cutover | `build_layout_le.py --as-live` | the cut-over candidate `output/trial/tables_cutover.xml`; the live `tables.xml` took it at the cut-over |
| le-cutover-devicemap | `build_layout_le.py --as-live --staging devicemap --review` | the same candidate with staging drawn from the staging device map and `panel_items.json` (no frozen file, no overlay): `output/trial/tables_cutover_devicemap.xml` and `_devicemap_staging.xml`, for the owner's review |
| staged-boundaries | `build_staging_candidate.py` | `schematic/staged/le_signal_boundaries.csv` for that candidate's generated anchor idents, and a report and images that set it beside the frozen candidate |

Each step reads the plugin's cache (`~/.cache/hart/schematic`), so a run after a small change redoes only what that
change reaches. `tools/check.sh` runs `--check` on the hands, signals, device map, main and upper masts and CATS steps; `make panels
CHECK=1` checks them all.

## After a run

- `tables.xml` changed: `make panelpro-test`, then deploy (AGENTS.md close-out).
- A schematic drawing changed: refresh the evolution GIF (`tools/schematic/evolution.py`).

Detail: [`wiki/projects/schematic-maps-handoff.md`](../projects/schematic-maps-handoff.md) ·
[`docs/ops/schematic-system-draft.md`](../../docs/ops/schematic-system-draft.md)
