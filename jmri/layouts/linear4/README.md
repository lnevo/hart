# Layout: linear4

**Status (May 2026):** Production JMRI panel is **`output/linear4_prod.xml`** — geometry from AnyRail, 18 turnouts, 47 blocks, live MQTT hardware from root `tables.xml`, operator labels, and LogixNG window helpers. Verified in JMRI.

**AI / full project context:** [`docs/AI_CONTEXT.md`](../../../docs/AI_CONTEXT.md)

AnyRail export: `anyrail/linear4.xml` (drop from repo root: `cp linear4.xml jmri/layouts/linear4/anyrail/linear4.xml`)

Geometry is used **1:1** from AnyRail — do **not** run `fit_panel_height`, `fit_panel_canvas`, or `polish_layout_geometry` unless the user explicitly asks.

---

## Three panel XML files

| File | Role | Open in JMRI when… |
|------|------|---------------------|
| `output/linear4_blocked.xml` | Track + blocks + internal occupancy sensors (no live MQTT) | Editing block map from Excel / AnyRail |
| `output/linear4_devices.xml` | Blocked geometry + **MQTT/IT devices**, labels, styling | Dev / comparing device wiring without LogixNG |
| **`output/linear4_prod.xml`** | **Production load** — same as devices + memories, timebase, LogixNG from `tables.xml` | **Normal operations** |

Live hardware source: repo root **`tables.xml`** (read-only for agents; edit `tables/new_tables.xml` for panel table changes).

---

## Pipeline A — Blocked panel (geometry + blocks)

```bash
export JMRI_LAYOUT=linear4

cp linear4.xml jmri/layouts/linear4/anyrail/linear4.xml

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

---

## Pipeline B — Production MQTT panel

After `linear4_blocked.xml` exists:

```bash
python3 jmri/scripts/generate_linear4_panel_background.py   # optional PNG for JMRI preferences
python3 jmri/scripts/build_linear4_device_mapping.py \
  --write-panel --write-prod-panel --dcc-label-placement split
```

**Load in JMRI:** `output/linear4_prod.xml`

### What the builder does

- **Geometry:** `linear4.xml` (1280×320), AnyRail background image stripped (`linear4.jpg` causes load errors).
- **Devices:** 16 **MQTT** turnouts (`M2T*`, user names `MQTT Switch …`) + 2 **internal** crossover legs (`IT1`, `IT36`) with MQTT feedback sensors; Signal Mast 1 from live panel.
- **Blocks:** 47 blocks from `linear4_blocked.xml`; turnout block **comments** use MQTT names (e.g. `MQTT Switch 3-8`), mapped via `data/turnout_mapping.csv`.
- **Labels:** DCC addresses 100–115 (`split` placement preset in `data/dcc_label_placement.json`); area titles (Neville Island, yards, PIR, direction row).
- **Style:** Mac-derived layout defaults; light blue panel RGB `(186, 210, 235)` — **no** embedded `preference:` background image in XML (loads cleanly without copying PNG).
- **XML shape (JMRI 5.15.5):** `jmriversion` 5.15.5; internal sensor manager `defaultInitialState` + `ISCLOCKRUNNING`; turnout `operations` on MQTT and internal managers; `blocks` / `layoutblocks` **before** `LayoutEditor`.

**Prod merge** (`merge_linear4_prod_panel.py`): inserts from `tables.xml` before layout — `memories`, `signalmastlogics`, `timebase`, LogixNG (WiThrottle / Console / Power Control minimize helpers).

### Hardware map (authoritative)

Curated in `jmri/scripts/build_linear4_device_mapping.py` → `data/turnout_mapping.csv`:

- 18 linear4 layout idents (`TOL3`, `TOR14`, …) → unique `M2T*` motors where possible.
- Crossover slave legs: `TOL1` → `IT1`, `TOR32` → `IT36` (same MQTT motor as paired main leg).
- DCC addresses 100–115 on panel labels (switch ids `4-8` … `1-10` in CSV).

Edit `CURATED_PANEL_SYSTEM` in the script if hardware assignment changes, then regenerate CSVs and panels.

---

## Pipeline C — Dispatcher / NextTrain

```bash
export JMRI_LAYOUT=linear4
cp jmri/layouts/linear4/output/linear4_blocked.xml \
  jmri/layouts/linear4/dispatcher/tables.xml
python3 dispatcher/scripts/jmri_layout_to_nexttrain_xlsx.py --whole-layout
# Or one-shot: ./dispatcher/scripts/sync_layout_to_google_sheets.sh
```

Schematic transform: `dispatcher/export_options.json` (`segment_scale` / `control_point_scale` **2.5**, offsets 48×36). See [`docs/AI_CONTEXT.md`](../../../docs/AI_CONTEXT.md).

---

## Outputs & data files

| Path | Description |
|------|-------------|
| `authoritative/linear4.xml` | Prepared panel (scale 1, mac drawing options) |
| `data/layout_blocks.xlsx` | Block map |
| `data/turnout_mapping.csv` | linear4 ident ↔ live MQTT/IT/DCC |
| `data/sensor_mapping.csv` | Feedback + block occupancy placeholders |
| `data/dcc_label_placement.json` | DCC label Y offsets (`split` / `uniform`) |
| `data/layout_area_labels.json` | Area label positions |
| `assets/linear4_panel_bg.png` | Optional river background (install to JMRI preferences) |
| `output/linear4_blocked.xml` | Blocks + layout, no live MQTT |
| `output/linear4_devices.xml` | Dev panel (devices, no LogixNG) |
| **`output/linear4_prod.xml`** | **Production panel** |
| `dispatcher/tables.xml` | Copy for NextTrain export |
| `dispatcher/NextTrainDispatcherApp.xlsx` | Dispatcher workbook |
| `dispatcher/export_options.json` | Schematic scale + margin |

See also [`data/README.md`](data/README.md), [`assets/README.md`](assets/README.md).

---

## Scripts (linear4-specific)

| Script | Role |
|--------|------|
| `build_linear4_device_mapping.py` | CSVs + `linear4_devices.xml` / `linear4_prod.xml` |
| `merge_linear4_prod_panel.py` | Merge LogixNG stack from `tables.xml` into prod panel |
| `generate_linear4_panel_background.py` | Regenerate `assets/linear4_panel_bg.png` |

Shared JMRI tools: `prepare_tables_from_anyrail.py`, `build_blocks_excel.py`, `apply_blocks_to_panel.py` (see [`jmri/docs/PROJECT_OVERVIEW.md`](../../docs/PROJECT_OVERVIEW.md)).
