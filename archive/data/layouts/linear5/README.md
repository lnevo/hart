# Layout: linear5

**Goal:** Same track plan as **linear4**, with **more vertical spacing** between parallel tracks.

**Status:** Restarted from linear4 — Y-spread **4.0** + **A48 arc** only (no leveling).

**AI context:** [`docs/AI_CONTEXT.md`](../../../docs/AI_CONTEXT.md) · **linear4 reference:** [`../linear4/README.md`](../linear4/README.md)

---

## Current pipeline (from linear4)

```bash
jmri/scripts/build_linear5_from_linear4.sh 4.0
```

Or step by step:

```bash
# 1. Y-spread from linear4 anyrail
python3 jmri/scripts/spread_layout_y.py \
  jmri/layouts/linear4/anyrail/linear4.xml \
  jmri/layouts/linear5/working/linear5_spread_4.0.xml \
  --factor 4.0 --layout-name linear5

# 2. East-end arc only (A48 X outward — no leveling)
python3 jmri/scripts/polish_linear5_geometry.py \
  jmri/layouts/linear5/working/linear5_spread_4.0.xml \
  jmri/layouts/linear5/working/linear5_spread_4.0_arc.xml \
  --arc-x-scale 4.0

# 3. Mac drawing options + blocks
python3 jmri/scripts/prepare_tables_from_anyrail.py \
  jmri/layouts/linear5/working/linear5_spread_4.0_arc.xml \
  jmri/layouts/linear5/anyrail/linear5.xml \
  jmri/layouts/mac/authoritative/mac_jmri2.xml \
  --scale 1

export JMRI_LAYOUT=linear5
cd jmri && python3 scripts/apply_blocks_to_panel.py \
  layouts/linear5/anyrail/linear5.xml \
  layouts/linear5/output/linear5_blocked_generated.xml \
  layouts/mac/authoritative/mac_jmri2.xml \
  use-panel-layout no-nx
```

**Open in JMRI (manual geometry):** `output/linear5_blocked.xml`  
**Production load (MQTT + LogixNG):** `output/linear5_prod.xml`  
**Protected backup:** `reference/linear5_manual_save.xml` (synced with output)  
**Pipeline output (safe to regenerate):** `output/linear5_blocked_generated.xml`

### Production panel (same as linear4_prod)

After `linear5_blocked.xml` has your tuned geometry:

```bash
python3 jmri/scripts/build_linear4_device_mapping.py \
  --layout linear5 \
  --write-panel \
  --write-prod-panel \
  --dcc-label-placement split
```

**Load in JMRI:** `output/linear5_prod.xml`

| File | Role |
|------|------|
| `output/linear5_devices.xml` | Geometry + MQTT/IT devices, labels, styling (no LogixNG) |
| **`output/linear5_prod.xml`** | **Production** — devices + memories, timebase, LogixNG from `tables.xml` |

Uses the same hardware map as linear4 (`CURATED_PANEL_SYSTEM` in `build_linear4_device_mapping.py`).  
Label tuning: `data/dcc_label_placement.json`, `data/layout_area_labels.json`.

**Track Y shift (area labels stay fixed):** align upper main to linear4 via EB70:

```bash
python3 jmri/scripts/shift_layout_track_y.py \
  jmri/layouts/linear5/output/linear5_blocked.xml \
  --align-anchor EB70 --target-y 168.11 --bottom-margin 32
cp jmri/layouts/linear5/output/linear5_blocked.xml \
  jmri/layouts/linear5/reference/linear5_manual_save.xml
# Then rebuild devices/prod (DCC labels follow turnouts; area labels use layout_area_labels.json)
```

### What changes vs linear4

| Step | Effect |
|------|--------|
| `spread_layout_y.py` | All track Y scaled 4× from pivot (~178); X unchanged; beziers scaled once |
| `polish_linear5_geometry.py` (default) | **A48** arc; targeted fixes (A64/A2/A52 removed, F51 A49→TOL42, A60/A21 diverge X, F39 dropped, EB73↔A21) |
| `--level` flag (optional, off) | Bulk anchor snap + horizontal level — skipped for now |

### linear4 vs linear5 @ 4.0

| Metric | linear4 | linear5 |
|--------|---------|---------|
| Track Y band | ~146–210 | ~50–306 |
| A48 x | ~1202 | ~**1255** |
| Panel | 1280×320 | 1280×355 |
| Turnouts / blocks | 18 / 47 | 18 / 47 |

**Do not use** on linear5 unless asked: `fit_panel_height` rebase, `fit_panel_canvas`, `polish_layout_geometry`, 2× draw scale.

### West-yard trackwork (drawn in JMRI)

New segments (`T1`, `T3`–`T13`) and turnouts (`TO1`, `TO6`, `TO8`, `TO10`, `TO11`) are merged from `output/linear5_new.xml` via `process_linear5_new_panel.py`.

**Checklist after adding yard geometry:**

1. Blocks assigned (each switch its own block; AUTOBLK renamed to `Block_N`)
2. Internal occupancy sensors (`ISIS*`, userName `Block Sensor N` or `BS TO*`)
3. **`mainline="yes"`** on new segments and yard turnouts — editor-drawn track defaults to sidetrack (`mainline="no"`); mismatched flags make blocks look wrong in the panel

```bash
python3 jmri/scripts/process_linear5_new_panel.py jmri/layouts/linear6/linear5_new.xml
```

---

## Files

| Path | Purpose |
|------|---------|
| `working/linear5_spread_4.0.xml` | After Y-spread from linear4 |
| `working/linear5_spread_4.0_arc.xml` | After A48 arc adjust |
| `anyrail/linear5.xml` | Prepared geometry |
| `output/linear5_blocked.xml` | Manual geometry + blocks |
| `output/linear5_devices.xml` | Dev panel (devices, no LogixNG) |
| **`output/linear5_prod.xml`** | **Production panel** |
| `reference/linear5_manual_save.xml` | Backup copy of `output/linear5_blocked.xml` |
| `output/linear5_blocked_generated.xml` | Regenerated from anyrail + blocks (pipeline only) |
| `data/turnout_mapping.csv` | linear5 ident ↔ live MQTT/IT/DCC |
| `data/dcc_label_placement.json` | DCC label Y offsets (Y-spread layout) |
| `data/layout_area_labels.json` | Area / direction label positions |

```bash
export JMRI_LAYOUT=linear5
```
