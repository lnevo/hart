# Layout: hart

**Status:** Next-gen HART panel (phases 0–2) — naming + cleanup from linear6.

**SoR:** [`wiki/projects/hart-panel.md`](../../../wiki/projects/hart-panel.md) · ADRs 001–003

## Principles

- **Name:** `hart` · `export JMRI_LAYOUT=hart`
- **Connectivity / positions:** from the AnyRail panel (`anyrail/hart.xml`)
- **JMRI config:** `output/tables.xml` is the one tables file (ADR-008)
- **Public names:** [ADR-005](../../../wiki/decisions/ADR-005-public-equipment-names.md) map `data/public_name_map.csv`
- Do **not** run `fit_panel_height`, `fit_panel_canvas`, or `polish_layout_geometry` unless explicitly asked

## Bootstrap

```bash
export JMRI_LAYOUT=hart
python3 jmri/scripts/bootstrap_hart_from_linear6.py
```

For the complete live configuration, deploy/load **`output/tables.xml`**. It
contains the Layout Editor, native SML, Dispatcher System, and USS CTC data.

| Path | Role |
|------|------|
| `anyrail/hart.xml` | Geometry source snapshot |
| `output/tables.xml` | The one tables file: LE + SML + Dispatcher + CTC. JMRI loads it and deploy ships it |
| `data/public_name_map.csv` | Apply map (`current` live identity, `proposed` next pass, `comment` from Device map) |
| `data/control_points.csv` | CP → switches |
| `data/sensor_purge_report.txt` | Removed unused ISIS\* |

## Maintenance scripts

```bash
python3 jmri/scripts/cleanup_hart_duplicate_blocks.py   # drop empty duplicate <block> rows
python3 jmri/scripts/polish_hart_cp_labels.py           # CP/area label hierarchy
python3 jmri/scripts/export_hart_devices_for_cats.py    # CATS Designer bindings
python3 jmri/scripts/check_hart_phase02.py
python3 jmri/layouts/hart/scripts/polish_hart_layout_editor.py --check
python3 jmri/layouts/hart/scripts/audit_panel_contracts.py
python3 jmri/layouts/hart/scripts/sync_public_name_map.py   # Device-map CSV identity + comments
python3 jmri/layouts/hart/scripts/reconcile_dispatcher_stations.py --check --no-sync

```

Visual scripts patch `output/tables.xml`.

Dispatcher stations are the original mainline eight (OS Main West, OS West Main Ext,
OS McKees Rocks, OS McKeesport, OS East Lead, OS Main East, OS East Main Ext,
OS Brick-Plane) plus OS EH-1–3, OS S-R–5, OS Scale (T1),
OS Barn (T6), OS W-1–2, and OS K-1 / OS K-2. The generated graph covers all 22
as origins and destinations (91 sections / 688 transits / 1508 HEAD_AND_TAIL traininfo).
OS S-R…OS S-4 are arrival/departure tracks; trains enter and leave via 103 or OS East Lead.

Operator guide (click destinations or named station lists):
[`dispatcher/DISPATCHER_GUIDE.md`](dispatcher/DISPATCHER_GUIDE.md).

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
