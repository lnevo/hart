# Panel workspace

Two related pipelines live here. Keep them in separate folders so a new AnyRail export does not overwrite dispatcher inputs or the finished Mac layout.

## Pipelines

| Goal | Folder | What you produce |
|------|--------|------------------|
| **1. JMRI panel** | [`jmri/`](jmri/) | Blocked panel XML for JMRI (`mac_jmri_blocked.xml`) |
| **2. Track warrants** | [`dispatcher/`](dispatcher/) | `NextTrainDispatcherApp.xlsx` segments / control points |

**Flow:** AnyRail export → apply defaults & blocks → JMRI panel → export tables/layout → NextTrain spreadsheet.

## Layouts (JMRI)

Each layout has its own tree under `jmri/layouts/<name>/`:

- `anyrail/` — AnyRail export (track geometry)
- `authoritative/` — JMRI panel with defaults, turnouts table, labels
- `data/` — `layout_blocks.xlsx`, `block_merges.txt`
- `output/` — final blocked panel, `nx_pairs.txt`
- `working/` — experiments and one-off intermediates

| Layout | Status |
|--------|--------|
| [`hart`](jmri/layouts/hart/) | **Next-gen (active)** — from linear6; CP/OS naming; `output/hart_prod.xml` |
| [`linear6`](jmri/layouts/linear6/) | Live hand-tuned reference (connectivity/positions for hart) |
| [`mac`](jmri/layouts/mac/) | Completed reference layout (do not overwrite for new AnyRail work) |
| [`linear4`](jmri/layouts/linear4/) | Prior production — `output/linear4_prod.xml`, dispatcher + Google Sheets |
| [`linear5`](jmri/layouts/linear5/) | Experiment — wider Y track spacing |
| [`linear3`](jmri/layouts/linear3/) | Earlier attempt; resize/polish experiments |
| [`new`](jmri/layouts/new/) | Placeholder to copy when starting another line |

```bash
export JMRI_LAYOUT=hart
python3 jmri/scripts/bootstrap_hart_from_linear6.py
python3 jmri/scripts/check_hart_phase02.py
```

**AI / handoff:** [`wiki/home.md`](wiki/home.md), [`docs/AI_CONTEXT.md`](docs/AI_CONTEXT.md), [`AGENTS.md`](AGENTS.md).

## Other folders

| Folder | Purpose |
|--------|---------|
| [`tables/`](tables/) | Git repo for JMRI table XML (`tables.xml` source, `new_tables.xml` output) |
| [`legacy/`](legacy/) | Superseded XML and misc CSV from earlier root clutter |
| [`NextTrainDispatcherApp/`](NextTrainDispatcherApp/) | Next.js app (separate git clone) |

## Quick commands

```bash
# Pipeline 1 — refresh geometry from AnyRail, keep Mac defaults
export JMRI_LAYOUT=mac
python3 jmri/scripts/apply_blocks_to_panel.py \
  jmri/layouts/mac/anyrail/upper_both4.xml \
  jmri/layouts/mac/output/mac_jmri_blocked.xml \
  jmri/layouts/mac/authoritative/mac_jmri2.xml \
  use-panel-layout

# Pipeline 2 — linear4: export + push to Google Sheets (see dispatcher/README.md)
export JMRI_LAYOUT=linear4
./dispatcher/scripts/sync_layout_to_google_sheets.sh
```

Full JMRI workflow (Mac blocks/sensors): [`jmri/docs/PROJECT_OVERVIEW.md`](jmri/docs/PROJECT_OVERVIEW.md).  
Dispatcher + Google Sheets detail: [`docs/AI_CONTEXT.md`](docs/AI_CONTEXT.md).
