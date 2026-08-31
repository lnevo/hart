> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record (consolidation view)

| Kind | Live path (read-only) | Proposed consolidation path |
|------|----------------------|----------------------------|
| Runbook | `wiki/pipelines/jmri-anyrail.md` | `consolidation/wiki/pipelines/jmri-anyrail.md` |
| Artifacts | See live guide below | `consolidation/sor/` when promoted |

---

# Pipeline 1 — JMRI AnyRail panel

Turn an AnyRail export into a blocked JMRI panel (occupancy, NX list, Mac defaults).

**Status:** Frozen for **hart**. Live geometry came from linear6; do not re-run this path unless asked. Still the workflow for `mac` / `linear4`.

## Inputs

- `jmri/layouts/<name>/anyrail/*.xml`
- `jmri/layouts/<name>/data/layout_blocks.xlsx` (+ `block_merges.txt`)
- Authoritative panel for styles (`mac_jmri2.xml` pattern)

## Outputs

- `jmri/layouts/<name>/output/*_blocked.xml`
- linear4 also `linear4_prod.xml` (MQTT + LogixNG)

## Run (`JMRI_LAYOUT=linear4` example)

```bash
export JMRI_LAYOUT=linear4
python3 jmri/scripts/prepare_tables_from_anyrail.py \
  jmri/layouts/linear4/anyrail/linear4.xml \
  jmri/layouts/linear4/authoritative/linear4.xml \
  --scale 1
python3 jmri/scripts/build_blocks_excel.py
python3 jmri/scripts/apply_blocks_to_panel.py \
  jmri/layouts/linear4/anyrail/linear4.xml \
  jmri/layouts/linear4/output/linear4_blocked.xml \
  jmri/layouts/mac/authoritative/mac_jmri2.xml \
  use-panel-layout no-nx
```

hart bootstrap (one-time, already done): `python3 jmri/scripts/bootstrap_hart_from_linear6.py`

## Do not

- `--scale` other than 1 on linear4/hart
- `fit_panel_height`, `fit_panel_canvas`, `polish_layout_geometry` unless asked
- Remove **F30-S-0** where the layout includes it
- New track: set **Mainline → Yes** (`mainline="yes"`)

Detail: [`jmri/README.md`](../../jmri/README.md) · [`docs/AI_CONTEXT.md`](../../docs/AI_CONTEXT.md)
