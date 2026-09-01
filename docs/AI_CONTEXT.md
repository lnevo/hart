# Panel workspace — context for AI assistants

**Live pipeline inventory (16 flows, NextTrain not listed):** [`wiki/pipelines/README.md`](../wiki/pipelines/README.md).

This document is still the landmine list for **linear4** AnyRail geometry and the **abandoned** NextTrain Google Sheets flow. hart does not re-run either. Read [`wiki/home.md`](../wiki/home.md) first.

---

## What this project is

**Panel** is a workspace for a model railroad JMRI layout. Historically two pipelines shared geometry:

| Pipeline | Folder | Output | Consumer |
|----------|--------|--------|----------|
| **1. JMRI panel** | `jmri/` | Blocked panel (`*_blocked.xml`); linear4 also **`linear4_prod.xml`** (MQTT + LogixNG) | JMRI Layout Editor |
| **2. Dispatcher schematic (abandoned for hart)** | `dispatcher/` + per-layout `jmri/layouts/<name>/dispatcher/` | `NextTrainDispatcherApp.xlsx` → Google Sheets | `NextTrainDispatcherApp/` (Next.js) |

**linear4 flow:** AnyRail export → prepare (optional) → blocks Excel → apply blocks → JMRI panel → export coordinates → local xlsx → **push to Google Sheets** → app reads live sheet.

---

## Repository layout

```
Panel/
  README.md                 # Human quick start
  docs/AI_CONTEXT.md        # This file (AI handoff)
  AGENTS.md                   # Pointer for agent tools
  .env.local                  # Google Sheets credentials (gitignored; copy from NextTrain setup)
  jmri/
    layout_paths.py           # JMRI_LAYOUT → paths (anyrail, output, dispatcher, …)
    scripts/                  # Python JMRI tools
    layouts/
      mac/                    # Completed reference layout (do not overwrite for new work)
      linear3/                # Earlier line; skewed by resize/polish experiments — avoid as template
      linear4/                # Production MQTT panel (1:1 geometry)
      linear5/                # linear4 + Y-spread experiments (wider track spacing)
      linear6/                # Live hand-tuned reference (connectivity/positions)
      hart/                   # Next-gen HART panel (from linear6; phases 0–2)
  dispatcher/
    scripts/jmri_layout_to_nexttrain_xlsx.py
    scripts/sync_layout_to_google_sheets.sh
    exports/NextTrainDispatcherApp.xlsx   # Template workbook (copied per layout on first export)
  NextTrainDispatcherApp/     # Separate Next.js app (own git); uses Google Sheets API
  tables/                     # Legacy JMRI tables XML repo (tables.xml = read-only source)
```

---

## Environment variable: `JMRI_LAYOUT`

Most scripts resolve paths via `jmri/layout_paths.py`:

```bash
export JMRI_LAYOUT=hart   # next-gen; or linear4, linear5, mac, linear3
```

Registered layouts in `layout_paths.py`: `mac`, `linear3`, `linear4`, `linear5`, **`hart`**. Each has `anyrail/`, `authoritative/`, `data/`, `output/`, `working/`, and **`dispatcher/`** (hart/linear5 dispatcher not wired yet).

### hart (next-gen, active)

- **SoR:** [`wiki/projects/hart-panel.md`](../wiki/projects/hart-panel.md), ADRs 001–003
- **Baseline:** linear6 connectivity/positions; JMRI profile/tables unchanged — **panel only**
- **Bootstrap:** `python3 jmri/scripts/bootstrap_hart_from_linear6.py`
- **Load:** `jmri/layouts/hart/output/hart_prod.xml`
- **Checks:** `python3 jmri/scripts/check_hart_phase02.py`
- Phases 0–2: naming (CP/OS), purge unused `ISIS*` sensors; signals/NX/NextTrain later
- **CATS CTC:** [`cats/README.md`](../cats/README.md) · ADR-004 · fetch `./tools/cats/fetch_cats_3.2.sh` (JMRI ≤5.16). Designer redraw binds hart user names; LE panel remains hardware monitor.

---

## Pipeline 1 — JMRI (linear4 example)

### Principles (do not regress)

- **Geometry 1:1 from AnyRail** — use `--scale 1` in `prepare_tables_from_anyrail.py`. Do **not** apply legacy 2× draw scale to linear3/linear4.
- **Do not run** on linear4 unless the user asks:
  - `fit_panel_height.py` (rebase mode shifts Y and skews the plan)
  - `fit_panel_canvas.py` (changes panel/window size; user may do this manually in JMRI)
  - `polish_layout_geometry.py` (straightens beziers / rounds coords; broke JMRI integer attrs on LayoutEditor `x`/`y`)
- **`use-panel-layout`** when applying blocks: track geometry from AnyRail export; styles/defaults from `mac_jmri2.xml`; **no** mac-only hidden segments or labels copied onto the new line.
- **Mainline flag on new trackwork** — JMRI `<tracksegment mainline="yes">` uses `mainlinetrackwidth` (4px); `mainline="no"` uses `sidetrackwidth` (2px). Track drawn in Layout Editor defaults to **not** mainline. Engine-terminal sidings `T1`/`T3`/`T4`/`T6`/`T7`/`T9`–`T13` are intentionally **mainline=no**; `T5`/`T8` stay yes. `process_linear5_new_panel.py` preserves that split — do not blanket-force all yard idents to yes.
- **Do not remove `F30-S-0`** — it connects F51-S-0 and F26-S-0 via anchors (see `jmri/layouts/linear3/docs/F30_connectivity_investigation.md`). Same topology in linear4.
- **Dispatcher System is stock.** Do not monkey-patch `CreateTransits` / `CreateIcons` / `Startup.py`. If Stage 1 or Discover fails, fix `tables/new_tables.xml` (mast bindings, block boundaries). Never invent **Mast 26L → Mast 8RA**.

### Standard linear4 commands

```bash
export JMRI_LAYOUT=linear4

# Drop new export from repo root
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

Open in JMRI: `jmri/layouts/linear4/output/linear4_blocked.xml`.

### linear4 production panel (MQTT + LogixNG)

**Status:** Rolled to prod May 2026 — load **`jmri/layouts/linear4/output/linear4_prod.xml`** in JMRI for operations.

| Stage | Output | Contents |
|-------|--------|----------|
| Blocks | `linear4_blocked.xml` | 47 blocks, track geometry, internal BS sensors |
| Devices | `linear4_devices.xml` | + 16 MQTT + 2 IT turnouts, Signal Mast 1, labels, styling |
| **Prod** | **`linear4_prod.xml`** | + memories, timebase, LogixNG from root `tables.xml` |

```bash
python3 jmri/scripts/generate_linear4_panel_background.py   # optional; see layouts/linear4/assets/README.md
python3 jmri/scripts/build_linear4_device_mapping.py \
  --write-panel --write-prod-panel --dcc-label-placement split
```

**Sources:** AnyRail `linear4.xml` (geometry) + `linear4_blocked.xml` (blocks) + live **`tables.xml`** (MQTT/IT devices, LogixNG). Curated map: `jmri/layouts/linear4/data/turnout_mapping.csv` (`CURATED_PANEL_SYSTEM` in script).

**Panel features:** 1280×320; DCC labels 100–115; area/direction labels; turnout block comments = `MQTT Switch …`; light blue RGB background (no embedded preference image in XML).

**Generator XML rules (match JMRI save — do not regress):** JMRI **5.15.5** `jmriversion`; internal-sensor `defaultInitialState` + `ISCLOCKRUNNING`; turnout `operations` on MQTT and internal managers; internal turnouts manager **before** MQTT; `blocks` / `layoutblocks` **before** `LayoutEditor`; prod merge inserts `memories` before `signalheads`, then signalmastlogics/timebase/LogixNG before layout.

Detail: [`jmri/layouts/linear4/README.md`](../jmri/layouts/linear4/README.md).

### Mac layout

`jmri/layouts/mac/` is the **completed reference** for block/sensor conventions and JMRI styling. Use `mac_jmri2.xml` as style defaults for new lines; do not replace mac output when working on linear4.

---

## Pipeline 2 — Dispatcher / NextTrain app

### Purpose

The dispatcher app draws a **schematic** from Google Sheets tabs **Segments** and **ControlPoints**. Coordinates are **not** read from JMRI at runtime; they are **exported** from the blocked panel XML into a workbook, optionally transformed (scale + margin), then **pushed** to Google Sheets.

### Per-layout dispatcher folder

```
jmri/layouts/<name>/dispatcher/
  tables.xml                      # Copy of blocked panel (or use output path directly)
  NextTrainDispatcherApp.xlsx     # Local workbook (Segments + ControlPoints sheets)
  export_options.json             # Transform: segment_scale, control_point_scale, offset_x/y
  google_sheets.json              # Which env var holds the spreadsheet ID
```

**linear4 current transform** (`export_options.json`):

```json
{
  "segment_scale": 2.5,
  "control_point_scale": 2.5,
  "offset_x": 48,
  "offset_y": 36
}
```

- Rebases layout to bounding-box minimum, then scales **both** segment endpoints and control points by the same factor (keeps switches aligned with track).
- `segment_scale` / `control_point_scale` are independent in code but should stay equal unless the user wants deliberate misalignment.
- Adjust scale in `export_options.json`, re-export, re-push.

### Export script

`dispatcher/scripts/jmri_layout_to_nexttrain_xlsx.py`

- With `JMRI_LAYOUT` set, reads `dispatcher/tables.xml` (or `output/*_blocked.xml`) and writes `dispatcher/NextTrainDispatcherApp.xlsx`.
- Use **`--whole-layout`** for linear4 (full panel, not middle-third crop).
- Does **not** modify JMRI files.

**Columns K–T (connector lines):** Inferred automatically from JMRI topology unless `--no-infer-connections`. When two segments meet at the same anchor (`PT:…`) or turnout (`TO:…`) but their exported endpoints are farther apart than `connection_snap_tolerance` (default 6 sheet units, in `export_options.json`), the export fills:

| Col | Field |
|-----|--------|
| K | `connectsToSegmentId` |
| L–O | `connectionStartX/Y`, `connectionEndX/Y` |
| P–T | Second connection (`connectsToSegmentId2`, …) |

The app draws these as extra SVG paths (`track-segment.tsx`) so turnout legs and nearby blocks visually connect. Up to two connectors per segment row.

```bash
export JMRI_LAYOUT=linear4
cp jmri/layouts/linear4/output/linear4_blocked.xml \
  jmri/layouts/linear4/dispatcher/tables.xml
python3 dispatcher/scripts/jmri_layout_to_nexttrain_xlsx.py --whole-layout
```

### Google Sheets push (live app data)

Credentials: **`GOOGLE_SHEETS_CLIENT_EMAIL`**, **`GOOGLE_SHEETS_PRIVATE_KEY`** in:

- `Panel/.env.local` (user may place here), and/or
- `NextTrainDispatcherApp/.env.local`

The push script loads **both** paths (root first, then app).

Spreadsheet ID: env var from `google_sheets.json`, e.g. linear4 uses `GOOGLE_SHEETS_SPREADSHEET_ID` if no layout-specific var is set.

**Push script:** `NextTrainDispatcherApp/scripts/push-layout-xlsx-to-sheets.js`  
**npm:** `cd NextTrainDispatcherApp && npm run push-layout -- --layout linear4`

**Important:** Do **not** delete Google Sheet rows one-by-one (hits API 429 quota). The script uses `sheet.clear()` + `setHeaderRow` + `addRows` (batched).

**One-shot sync:**

```bash
export JMRI_LAYOUT=linear4
./dispatcher/scripts/sync_layout_to_google_sheets.sh
```

After push, user hard-refreshes the NextTrain app or re-selects the spreadsheet instance.

### NextTrain app

- Lives in `NextTrainDispatcherApp/` (separate git clone).
- Reads segments/control points via `/api/railroad-data/[spreadsheetId]`.
- Schematic stroke width is in React (`track-segment.tsx`); **layout size/position** comes from sheet coordinates only.
- Multiple layouts = multiple Google spreadsheets (or spreadsheet IDs in env); register each in the app UI.

---

## Key scripts reference

| Script | Role |
|--------|------|
| `jmri/layout_paths.py` | Paths for active layout (`JMRI_LAYOUT`) |
| `jmri/scripts/prepare_tables_from_anyrail.py` | AnyRail → authoritative; strip background labels; `--scale 1` for linear3/4 |
| `jmri/scripts/build_blocks_excel.py` | Layout XML → `data/layout_blocks.xlsx` |
| `jmri/scripts/apply_blocks_to_panel.py` | Excel + merges → blocked panel; `use-panel-layout`, mac defaults |
| `jmri/scripts/build_linear4_device_mapping.py` | linear4 ↔ `tables.xml` CSVs; `--write-panel` / `--write-prod-panel` |
| `jmri/scripts/merge_linear4_prod_panel.py` | LogixNG + memories + timebase → `linear4_prod.xml` |
| `jmri/scripts/generate_linear4_panel_background.py` | Optional `linear4_panel_bg.png` |
| `jmri/scripts/spread_layout_y.py` | Spread track Y spacing around pivot (linear5); X unchanged |
| `dispatcher/scripts/jmri_layout_to_nexttrain_xlsx.py` | tables.xml → xlsx + coordinate transform |
| `dispatcher/scripts/sync_layout_to_google_sheets.sh` | export + push |
| `NextTrainDispatcherApp/scripts/push-layout-xlsx-to-sheets.js` | xlsx → Google Sheets API |

---

## History / lessons

### May 2025 — linear3 → linear4, dispatcher

1. **linear3** — 2× draw scale and later `polish_layout_geometry` / canvas fitting **skewed** the plan. User restarted with **linear4** at 1:1.
2. **F4-S-0** bezier issue on linear3 was fixed by straightening; linear4 export uses **F68-S-0** (A69↔A68) as a straight segment instead.
3. **JMRI parse error** — `LayoutEditor` `x`/`y` must be **integers** (`1166` not `1166.0`). Polish script was fixed to not round LayoutEditor window attrs; avoid re-running broken polish on panels.
4. **Dispatcher zoom** — JMRI `xscale`/`yscale` are not the same as app schematic size; dispatcher uses **exported coordinates** with `segment_scale` / `control_point_scale` in `export_options.json`.
5. **Control points** must use the **same scale** as segments or switches/signals drift off track.
6. **Google push** succeeded after switching from per-row delete to `sheet.clear()` + bulk `addRows`.

### May 2026 — linear4 production MQTT panel

7. **Device panel built** — Merged AnyRail geometry with live `tables.xml`: 18 turnouts (16× MQTT `M2T*`, 2× crossover `IT1`/`IT36`), Signal Mast 1, 47 blocks, DCC/area labels, mac styling, `turnout_mapping.csv` / `sensor_mapping.csv`.
8. **Block comments** — Turnout blocks use operator names (`MQTT Switch 3-8`, …) from `turnout_mapping.csv`, not layout idents (`TOR14`).
9. **linear4_prod load errors** — Unsaved XML differed from JMRI save: wrong `jmriversion`, missing clock sensor / sensor defaults, internal turnouts without `operations`, blocks after `LayoutEditor`, broken `preference:/linear4_panel_bg.png` label. Fixed in `build_linear4_device_mapping.py` and `merge_linear4_prod_panel.py`; prod load verified.
10. **Prod rollout** — Operators use `output/linear4_prod.xml`; regenerate with `--write-prod-panel` after block or hardware changes (re-run blocked pipeline first if geometry/blocks change).

### June 2026 — linear5 west-yard trackwork

11. **Blocks looked missing** — New yard geometry had `blockname` and block-table entries, but segments were `mainline="no"` while the rest of the panel uses `mainline="yes"`. JMRI renders sidetrack width and block highlighting differently; fix is Mainline → Yes on new segments/turnouts in Layout Editor (see principles above). `process_linear5_new_panel.py` also sets mainline on yard idents when merging into `linear5_blocked.xml`.
12. **Yard block sensors** — Internal occupancy uses **`ISIS`** system names (not `IS`). ISIS48–83 are turnout feedback on linear5; yard block sensors were added at ISIS84+ with userNames `Block Sensor N` (track) or `BS TO*` (switch blocks), matching blocks 1–47 conventions.

---

## What to do when the user asks to…

| Request | Action |
|---------|--------|
| New AnyRail export | Copy to `anyrail/`, run prepare → build_blocks → apply_blocks (`use-panel-layout`), open `output/*_blocked.xml` |
| Add track in JMRI Layout Editor | Assign blocks + set **Mainline → Yes** on new segments/turnouts; for linear5 yard use `process_linear5_new_panel.py` (blocks, sensors, mainline flags) |
| Refresh linear4 prod panel | After blocked XML is current: `build_linear4_device_mapping.py --write-panel --write-prod-panel --dcc-label-placement split`; load `linear4_prod.xml` |
| Change MQTT / DCC mapping | Edit `CURATED_PANEL_SYSTEM` or hardware in `tables.xml`, regenerate mapping + prod panel |
| Update dispatcher view | Copy blocked XML to `dispatcher/tables.xml`, run xlsx export, run `npm run push-layout` |
| Change schematic size | Edit `dispatcher/export_options.json` scales, re-export + push (do not change JMRI panel for app-only sizing) |
| New layout name | Copy `jmri/layouts/new/` or linear4 tree, add entry to `layout_paths.py`, add `dispatcher/export_options.json` + `google_sheets.json` |
| Commit credentials | **Never** commit `.env.local` |

---

## Further reading

- [`jmri/docs/PROJECT_OVERVIEW.md`](../jmri/docs/PROJECT_OVERVIEW.md) — Mac layout blocks, sensors, apply_blocks detail
- [`dispatcher/README.md`](../dispatcher/README.md) — Dispatcher commands (kept in sync with this doc)
- [`jmri/layouts/linear4/README.md`](../jmri/layouts/linear4/README.md) — linear4-specific pipeline
- [`README.md`](../README.md) — Short human overview
