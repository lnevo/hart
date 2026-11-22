# Pipeline 1 — JMRI AnyRail panel

Turn an AnyRail export into a blocked JMRI panel (occupancy, NX list, Mac defaults).

**Status:** Retired and replaced by [schematic-panels.md](schematic-panels.md) (2026-11-17). The panels are drawn from the schematic now (`make panels`), and hart's main and upper levels were built that way. The four scripts below moved to `archive/jmri-scripts/`. They would still run if called by hand and would write panel XML from a stale export, so do not run them. This page is history.

## Inputs

- `jmri/layouts/<name>/anyrail/*.xml`
- `jmri/layouts/<name>/data/layout_blocks.xlsx` (+ `block_merges.txt`)
- Style template: `jmri/templates/panel_style.xml`

## Outputs

- `jmri/layouts/<name>/output/*_blocked.xml`

## How it ran (`JMRI_LAYOUT=hart` example)

```bash
export JMRI_LAYOUT=hart
python3 archive/jmri-scripts/prepare_tables_from_anyrail.py \
  jmri/layouts/hart/anyrail/hart.xml \
  jmri/templates/panel_style.xml \
  --scale 1
python3 archive/jmri-scripts/build_blocks_excel.py
python3 archive/jmri-scripts/apply_blocks_to_panel.py \
  jmri/layouts/hart/anyrail/hart.xml \
  jmri/layouts/hart/output/hart_blocked.xml \
  jmri/templates/panel_style.xml \
  use-panel-layout no-nx
```

hart bootstrap (one-time, already done; the script is kept for history at `archive/jmri-scripts/bootstrap_hart_from_linear6.py`). New levels come from the schematic (`make panels`), not from this pipeline.

## Do not

- `--scale` other than 1 on linear4/hart
- `fit_panel_height`, `fit_panel_canvas`, `polish_layout_geometry` (archived in `archive/jmri-scripts/`) unless asked
- New track: set **Mainline → Yes** (`mainline="yes"`)

Detail: [`jmri/README.md`](../../jmri/README.md)
