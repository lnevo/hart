# Layout: hart

**Status:** Next-gen HART panel (phases 0–2) — naming + cleanup from linear6.

**SoR:** [`wiki/projects/hart-panel.md`](../../../wiki/projects/hart-panel.md) · ADRs 001–003

## Principles

- **Name:** `hart` · `export JMRI_LAYOUT=hart`
- **Connectivity / positions:** frozen from linear6 (`reference/linear6_baseline.xml`)
- **JMRI config:** existing profile/tables; **panel XML only** changes (ADR-003)
- **Public names:** CP / OS contract in `data/block_display_names.csv` (ADR-002)
- Do **not** run `fit_panel_height`, `fit_panel_canvas`, or `polish_layout_geometry` unless explicitly asked

## Bootstrap

```bash
export JMRI_LAYOUT=hart
python3 jmri/scripts/bootstrap_hart_from_linear6.py
```

Open in JMRI: **`output/hart_prod.xml`** (same bytes as `hart_blocked.xml` after bootstrap).

| Path | Role |
|------|------|
| `reference/linear6_baseline.xml` | Frozen linear6 copy |
| `anyrail/hart.xml` | Geometry source snapshot |
| `authoritative/hart.xml` | Authoritative panel snapshot |
| `output/hart_blocked.xml` | Working blocked panel |
| `output/hart_prod.xml` | Load this for ops/dev |
| `data/block_display_names.csv` | Rename map |
| `data/control_points.csv` | CP → switches |
| `data/sensor_purge_report.txt` | Removed unused ISIS\* |

## Phase scope

| In (0–2) | Out |
|----------|-----|
| Register layout, naming, purge unused internals | Signals / SML |
| OS / CP documentation | NX Entry/Exit |
| Git + wiki SoR | NextTrain push / Pi cutover |
