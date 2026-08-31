> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record

| Kind | Live (read-only) | Consolidation draft |
|------|------------------|---------------------|
| Runbook | `wiki/pipelines/jmri-anyrail.md` | this file |
| hart panel | `jmri/layouts/hart/reference/linear6_baseline.xml` | — |
| AnyRail snapshot | `jmri/layouts/hart/anyrail/hart.xml` | historical only |

---

# Pipeline 1 — JMRI AnyRail panel

Turn an AnyRail export into a blocked JMRI panel (occupancy, NX list, Mac defaults).

## hart status: **not this pipeline**

**hart does not use AnyRail → Excel → blocked panel.** Geometry and connectivity were forked once from **linear6** (`bootstrap_hart_from_linear6.py`). Re-running AnyRail prep on hart would violate ADR-001/003 unless explicitly requested.

| Layout | Pipeline 1 role |
|--------|-----------------|
| **hart** | **Frozen** — linear6 bootstrap only |
| linear4 / mac / linear5 | Active AnyRail workflow below |

## Active workflow (non-hart layouts)

### Inputs

- `jmri/layouts/<name>/anyrail/*.xml`
- `jmri/layouts/<name>/data/layout_blocks.xlsx` (+ `block_merges.txt`)
- Authoritative panel for styles (`mac_jmri2.xml` pattern)

### Outputs

- `jmri/layouts/<name>/output/*_blocked.xml`
- linear4 also `linear4_prod.xml` (MQTT + LogixNG)

### Run (`JMRI_LAYOUT=linear4` example)

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

### hart one-time bootstrap (already done)

```bash
export JMRI_LAYOUT=hart
python3 jmri/scripts/bootstrap_hart_from_linear6.py
```

## Do not (hart)

- Re-run AnyRail prep or `--scale` ≠ 1 on hart
- `fit_panel_height`, `fit_panel_canvas`, `polish_layout_geometry` unless asked
- Remove **F30-S-0** where the layout includes it
- New track without **Mainline → Yes** (`mainline="yes"`)

Detail: [`jmri/README.md`](../../../jmri/README.md) · [`docs/AI_CONTEXT.md`](../../../docs/AI_CONTEXT.md)
