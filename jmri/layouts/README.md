# JMRI layouts

One subdirectory per physical layout / AnyRail project.

## Standard layout

```
layouts/<name>/
  anyrail/          AnyRail export XML (e.g. upper_both4.xml)
  authoritative/    JMRI panel: defaults, turnouts table, labels
  data/             layout_blocks.xlsx, block_merges.txt
  output/           mac_jmri_blocked.xml, nx_pairs.txt
  working/          scratch XML, linear alignment, experiments
```

## Layouts in this repo

| Name | Use |
|------|-----|
| **mac** | Completed reference — block/sensor conventions; `mac_jmri2.xml` as style defaults |
| **linear4** | Active AnyRail line (1:1 geometry); has `dispatcher/` for NextTrain export + Google Sheets |
| **linear3** | Superseded; do not use resize/polish steps as a template |
| **new** | Copy when starting another line |

Each layout may include:

```
dispatcher/
  tables.xml
  NextTrainDispatcherApp.xlsx
  export_options.json      # segment_scale, control_point_scale, offset_x/y
  google_sheets.json       # spreadsheetIdEnv → .env.local
```

See [`docs/AI_CONTEXT.md`](../../docs/AI_CONTEXT.md).

## Starting the new layout

1. Copy `new/` to `layouts/<yourname>/` (or work directly in `new/`).
2. Put the AnyRail export in `anyrail/` (any filename; pass the path to `apply_blocks_to_panel.py`).
3. Build or copy an authoritative panel into `authoritative/`.
4. Run `build_blocks_excel.py` against the geometry, then edit `data/layout_blocks.xlsx`.
5. Set `export JMRI_LAYOUT=<yourname>` or pass explicit paths on every command.
