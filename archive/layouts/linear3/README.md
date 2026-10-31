# Layout: linear3

AnyRail export: `anyrail/linear3.xml`

## Outputs

| File | Description |
|------|-------------|
| `authoritative/linear3.xml` | Prepared panel (2× scale, drawing options) |
| `data/layout_blocks.xlsx` | Block map (29 track blocks + 18 turnout blocks) |
| `data/block_merges.txt` | Merge list (empty; add pairs as needed) |
| `output/linear3_blocked.xml` | Full JMRI panel with blocks & sensors |
| `output/nx_pairs.txt` | Entry/Exit pairs (if NX enabled later) |
| `dispatcher/inputs/tables.xml` | Copy of blocked panel for NextTrain |
| `dispatcher/exports/NextTrainDispatcherApp.xlsx` | Segments with block names |

## Full pipeline

```bash
export JMRI_LAYOUT=linear3

cp linear3.xml jmri/layouts/linear3/anyrail/linear3.xml

python3 jmri/scripts/prepare_tables_from_anyrail.py \
  jmri/layouts/linear3/anyrail/linear3.xml \
  jmri/layouts/linear3/authoritative/linear3.xml \
  --scale 1

python3 jmri/scripts/fit_panel_height.py \
  jmri/layouts/linear3/authoritative/linear3.xml --height-only --bottom 28

python3 jmri/scripts/build_blocks_excel.py
python3 jmri/scripts/apply_blocks_to_panel.py \
  jmri/layouts/linear3/anyrail/linear3.xml \
  jmri/layouts/linear3/output/linear3_blocked.xml \
  jmri/layouts/mac/authoritative/mac_jmri2.xml \
  use-panel-layout no-nx

cp jmri/layouts/linear3/output/linear3_blocked.xml dispatcher/inputs/tables.xml
python3 jmri/scripts/fit_panel_canvas.py \
  jmri/layouts/linear3/output/linear3_blocked.xml
# Or after resizing in JMRI: pass saved sizes explicitly:
#   --width 1254 --height 319
python3 dispatcher/scripts/jmri_layout_to_nexttrain_xlsx.py --whole-layout
```

**Connectivity note:** `F30-S-0` links F51-S-0 and F26-S-0 via anchors A51/A3 — do not remove. See [`docs/F30_connectivity_investigation.md`](docs/F30_connectivity_investigation.md).
