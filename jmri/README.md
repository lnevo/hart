# JMRI scripts

The panels are drawn from the schematic (`make panels`, `tools/schematic/`). The AnyRail pipeline that built the first
blocked panel (`prepare_tables_from_anyrail.py`, `sync_linear_panel.py`, `build_blocks_excel.py`,
`apply_blocks_to_panel.py`) is retired and kept in `archive/jmri-scripts/`; see
[`wiki/pipelines/jmri-anyrail.md`](../wiki/pipelines/jmri-anyrail.md).

## Per-layout folders

See [`layouts/README.md`](layouts/README.md). Active layout is **`hart`** (`export JMRI_LAYOUT=hart`).

## Scripts (`scripts/`)

| Script | Role |
|--------|------|
| `signal_coordinator.py` | Jython in JMRI on the Pi: hands the Digicon heads between SML and MQTT (SML Enabled / Disabled toggle) |
| `check_hart_phase02.py` | Acceptance checks for hart phases 0–2 (in `tools/check.sh`) |
| `generate_nx_pairs.py` | List Entry/Exit pairs for manual JMRI add (parked with NX; see `layouts/hart/parked/README.md`) |

## Documentation

Pipelines: [`wiki/pipelines/README.md`](../wiki/pipelines/README.md) · landmines: [`docs/AI_CONTEXT.md`](../docs/AI_CONTEXT.md)
