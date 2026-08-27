# Layout: hart

**Status:** Next-gen HART panel (phases 0–2) — naming + cleanup from linear6.

**SoR:** [`wiki/projects/hart-panel.md`](../../../wiki/projects/hart-panel.md) · ADRs 001–003

## Principles

- **Name:** `hart` · `export JMRI_LAYOUT=hart`
- **Connectivity / positions:** frozen from linear6 (`reference/linear6_baseline.xml`)
- **JMRI config:** existing profile/tables; **panel XML only** changes (ADR-003)
- **Public names:** [ADR-005](../../../wiki/decisions/ADR-005-public-equipment-names.md) map `data/public_name_map.csv`; live index `data/block_display_names.csv`
- Do **not** run `fit_panel_height`, `fit_panel_canvas`, or `polish_layout_geometry` unless explicitly asked

## Bootstrap

```bash
export JMRI_LAYOUT=hart
python3 jmri/scripts/bootstrap_hart_from_linear6.py
```

For the complete live configuration, deploy/load **`output/tables.xml`**. It
contains the Layout Editor, native SML, Dispatcher System, and USS CTC data.
`output/hart_prod.xml` is the standalone monitor-panel artifact and must not be
used to replace the complete tables bundle.

| Path | Role |
|------|------|
| `reference/linear6_baseline.xml` | Frozen linear6 copy |
| `anyrail/hart.xml` | Geometry source snapshot |
| `authoritative/hart.xml` | Authoritative panel snapshot |
| `output/hart_blocked.xml` | Working blocked panel |
| `tables/new_tables.xml` | Writable working source for the complete JMRI configuration |
| `output/tables.xml` | Deployment bundle: LE + SML + Dispatcher + CTC |
| `output/hart_prod.xml` | Standalone Layout Editor monitor artifact |
| `data/public_name_map.csv` | Apply map (`current` live, `proposed` next pass) |
| `data/block_display_names.csv` | Live CP / OS / track index |
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
python3 jmri/layouts/hart/scripts/reconcile_dispatcher_stations.py --check --no-sync
python3 jmri/layouts/hart/scripts/sync_hart_sml_to_deployment.py --check
```

Visual scripts patch each output independently; they never copy
`tables/new_tables.xml` over `output/tables.xml`, because that would remove the
CTC panel and `<ctcdata>`.

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
