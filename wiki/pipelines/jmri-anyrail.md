# Pipeline 1 — JMRI AnyRail panel

Turn an AnyRail export into a blocked JMRI panel (occupancy, NX list, Mac defaults).

**Status:** Frozen for **hart**: `hart_prod.xml` and `tables.xml` carry later JMRI work, so do not re-run unless asked. The tools stay live for future panels.

## Inputs

- `jmri/layouts/<name>/anyrail/*.xml`
- `jmri/layouts/<name>/data/layout_blocks.xlsx` (+ `block_merges.txt`)
- Style template: `jmri/templates/panel_style.xml`

## Outputs

- `jmri/layouts/<name>/output/*_blocked.xml`

## Run (`JMRI_LAYOUT=hart` example)

```bash
export JMRI_LAYOUT=hart
python3 jmri/scripts/prepare_tables_from_anyrail.py \
  jmri/layouts/hart/anyrail/hart.xml \
  jmri/templates/panel_style.xml \
  --scale 1
python3 jmri/scripts/build_blocks_excel.py
python3 jmri/scripts/apply_blocks_to_panel.py \
  jmri/layouts/hart/anyrail/hart.xml \
  jmri/layouts/hart/output/hart_blocked.xml \
  jmri/templates/panel_style.xml \
  use-panel-layout no-nx
```

hart bootstrap (one-time, already done): `python3 jmri/scripts/bootstrap_hart_from_linear6.py`

## Do not

- `--scale` other than 1 on linear4/hart
- `fit_panel_height`, `fit_panel_canvas`, `polish_layout_geometry` unless asked
- Remove **F30-S-0** where the layout includes it
- New track: set **Mainline → Yes** (`mainline="yes"`)

Detail: [`jmri/README.md`](../../jmri/README.md) · [`docs/AI_CONTEXT.md`](../../docs/AI_CONTEXT.md)
