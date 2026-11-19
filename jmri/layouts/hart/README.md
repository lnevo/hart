# Layout: hart

**Status:** Next-gen HART panel (phases 0–2) — naming + cleanup from linear6.

**SoR:** [`wiki/projects/hart-panel.md`](../../../wiki/projects/hart-panel.md) · ADRs 001–003

## Principles

- **Name:** `hart` · `export JMRI_LAYOUT=hart`
- **Connectivity / positions:** from the AnyRail panel (`anyrail/hart.xml`)
- **JMRI config:** `output/tables.xml` is the one tables file (ADR-008)
- **Public names:** [ADR-005](../../../wiki/decisions/ADR-005-public-equipment-names.md) map `data/public_name_map.csv`
- Do **not** run `fit_panel_height`, `fit_panel_canvas`, or `polish_layout_geometry` (archived in `archive/jmri-scripts/`) unless explicitly asked

## Bootstrap

The hart layout was bootstrapped once from the AnyRail panel; that script is kept for history at `archive/jmri-scripts/bootstrap_hart_from_linear6.py` and is not re-run, because `tables.xml` now carries later JMRI work. A new level or panel goes through the schematic pipeline ([`wiki/pipelines/schematic-panels.md`](../../../wiki/pipelines/schematic-panels.md)); the AnyRail pipeline it replaced is history ([`wiki/pipelines/jmri-anyrail.md`](../../../wiki/pipelines/jmri-anyrail.md)).

For the complete live configuration, deploy/load **`output/tables.xml`**. It
contains the Layout Editor and native SML. The Dispatcher System, Entry/Exit (NX) and USS CTC data are parked since the helix-join release (November 2026) and kept in `parked/`.

| Path | Role |
|------|------|
| `anyrail/hart.xml` | Geometry source snapshot |
| `output/tables.xml` | The one tables file: Layout Editor + SML. JMRI loads it and deploy ships it |
| `data/public_name_map.csv` | Apply map (`current` live identity, `proposed` next pass, `dcc` address, `comment` from Device map) |
| `data/control_points.csv` | CP → level, switches |
| `data/switches.csv` | Per switch: level, Layout Editor turnout, CATS inversion, USS CTC lever, hand (`scripts/layout_facts.py` reads it) |
| `data/mast_cells.csv` | Per mast: its cell on the USS CTC board's grid (the USS CTC machine is parked; the data is kept for unparking) and its icon (`gen_ctc_track_plan.py`); `edge`, `sig_location`, `sig_orient` are the hand-wired CATS desks' lamp placement (`check_layout_facts.py` reads them) |
| `data/uss_board_cells.csv`, `data/uss_board_plants.csv` | The USS CTC board's grid (each cell's track, label and block edges) and its switch plant cells, frozen from the hand-wired CATS desk on 2026-11-15, kept while the USS CTC machine is parked; read by `gen_ctc_track_plan.py` and `check_layout_facts.py` |
| `data/switch_legs.csv` | Per OS block at the points: the block the closed and thrown legs lead to |
| `data/sensor_purge_report.txt` | Removed unused ISIS\* |

## Maintenance scripts

```bash
python3 jmri/scripts/check_hart_phase02.py
python3 jmri/layouts/hart/scripts/audit_panel_contracts.py
python3 jmri/layouts/hart/scripts/sync_public_name_map.py   # Device-map CSV identity + comments

```

Visual scripts patch `output/tables.xml`.

**Parked:** the Dispatcher System, NX and the USS CTC machine (see [`parked/README.md`](parked/README.md), which
also lists the scripts that serve them). When the Dispatcher System was parked it had 12 stations (since 2026-11-12):
Track East Lead (button "East End"), K-1, K-2, McKees Rocks, McKeesport, Scale, Barn, EH-1–3, W-1 and W-2, with
187 transits and 374 HEAD_AND_TAIL traininfo. Its operator guide,
[`dispatcher/DISPATCHER_GUIDE.md`](dispatcher/DISPATCHER_GUIDE.md), applies again on unpark.

Layout Editor interaction layers are reserved as follows: signal icons level 9,
yard-ladder controls level 10, future track-side NX controls level 11, and
compact Dispatcher station status/command pairs level 12 beside their station
blocks.
Signal masts use JMRI's native AAR artwork at 1:1 icon scale. Duplicate
`Block n-n` occupancy sensor dots are intentionally omitted from the monitor;
the sensor beans remain available to Dispatcher, CTC, and signaling logic.

## CATS CTC

See [`cats/README.md`](../../../cats/README.md) and ADR-004. Layout Editor panel name is **HART**.

## Phase scope

| In (0–2 + continue) | Later |
|---------------------|--------|
| Register layout, naming, purge unused internals | Full SML in JMRI |
| OS / CP documentation + label hierarchy | NX Entry/Exit |
| Git + wiki SoR | NextTrain push / Pi cutover |
| CATS scaffold + Brick Designer guide | Live CATS interlocking |
