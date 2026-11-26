# Layout: mac (completed)

First full pass: AnyRail **`upper_both4.xml`**, authoritative **`mac_jmri2.xml`**, output **`mac_jmri_blocked.xml`**.

Treat this folder as **read-only reference** while building the new layout under `layouts/new/` (or a renamed copy). That avoids mixing block maps, merges, and panel XML between two AnyRail exports.

**Outputs used downstream:** `output/mac_jmri_blocked.xml` was the source for dispatcher `tables.xml` (see `dispatcher/inputs/`).

## Duplicates removed (2026-11-26)

These files were byte-identical to another archived file and were deleted. Use the copy named on the right.

| Removed | Same bytes as |
|---|---|
| `dispatcher/NextTrainDispatcherApp.xlsx` | `archive/code/nexttrain-dispatcher/exports/NextTrainDispatcherApp.xlsx` |
| `dispatcher/google_sheets.json` | `archive/data/layouts/linear4/dispatcher/google_sheets.json` |
