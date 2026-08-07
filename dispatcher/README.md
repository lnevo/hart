# NextTrain dispatcher pipeline

Convert a **JMRI panel / tables XML** into a **per-layout** `NextTrainDispatcherApp.xlsx` for the NextTrain dispatcher app.

## Per-layout outputs

Each layout has its own dispatcher folder (separate workbook + tables):

| Layout | Tables | Workbook |
|--------|--------|----------|
| mac | `jmri/layouts/mac/dispatcher/tables.xml` | `jmri/layouts/mac/dispatcher/NextTrainDispatcherApp.xlsx` |
| linear3 | `jmri/layouts/linear3/dispatcher/` | same pattern |
| linear4 | `jmri/layouts/linear4/dispatcher/` | same pattern |

Shared template (copied on first export): `dispatcher/exports/NextTrainDispatcherApp.xlsx`

## Schematic transform (baked into spreadsheet coords)

The export script rebases to the layout bounding box, then applies per-layout settings in `export_options.json`:

| Field | Purpose |
|-------|---------|
| `segment_scale` | Multiply segment endpoint coordinates (e.g. `2.5` = 2.5×) |
| `control_point_scale` | Multiply control-point coordinates — **keep equal to segment_scale** so switches align |
| `offset_x`, `offset_y` | Margin after scale (default 48, 36) |

**linear4 (current):** both scales **2.5**. This only affects the dispatcher app / Google Sheet, not JMRI panel geometry.

## Run

```bash
export JMRI_LAYOUT=linear4

cp jmri/layouts/linear4/output/linear4_blocked.xml \
  jmri/layouts/linear4/dispatcher/tables.xml

python3 dispatcher/scripts/jmri_layout_to_nexttrain_xlsx.py --whole-layout
```

With `JMRI_LAYOUT` set, paths default to that layout’s `dispatcher/` folder.

Legacy shared paths (no `JMRI_LAYOUT`): `dispatcher/inputs/tables.xml` and `dispatcher/exports/NextTrainDispatcherApp.xlsx`.

## Push to Google Sheets (live app data)

Uses the same service-account keys as the NextTrain app (`NextTrainDispatcherApp/.env.local`).

1. In **Panel root** `.env.local` and/or `NextTrainDispatcherApp/.env.local`, set `GOOGLE_SHEETS_CLIENT_EMAIL`, `GOOGLE_SHEETS_PRIVATE_KEY`, and `GOOGLE_SHEETS_SPREADSHEET_ID` (or a layout-specific var).
2. Optionally set `jmri/layouts/<layout>/dispatcher/google_sheets.json`:

```json
{
  "spreadsheetIdEnv": "GOOGLE_SHEETS_SPREADSHEET_ID_LINEAR4",
  "spreadsheetId": ""
}
```

3. Run export + push:

```bash
export JMRI_LAYOUT=linear4
./dispatcher/scripts/sync_layout_to_google_sheets.sh
```

Or manually:

```bash
cd NextTrainDispatcherApp && npm install && npm run push-layout -- --layout linear4
```

Segment and control-point coordinates use the same scale (see `export_options.json`; linear4 uses **2.5**).

**AI handoff:** [`docs/AI_CONTEXT.md`](../docs/AI_CONTEXT.md).

## App

The Next.js project lives at [`../NextTrainDispatcherApp/`](../NextTrainDispatcherApp/). Register each layout’s Google Sheet separately in the app (one spreadsheet ID per division/layout).
