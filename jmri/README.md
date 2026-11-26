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
| `signal_coordinator.py` | Jython in JMRI on the Pi: hands the Digicon heads between SML and MQTT (SML Enabled / Disabled toggle). It keeps the listener methods JMRI calls, the SML bulk set, the quit task and the re-run detach, and loads the modules below from the jython folder it runs in, reloading them on every run (`SIBLING_MODULES`) |
| `sml_beans.py` | Its constants, bean and name helpers, and the Digicon bean roster |
| `sml_claims.py` | Its claim parsing and ordering, the claim race between hosts, and the abort |
| `sml_handoff.py` | Its boot check, Enable and Disable steps, and each head's hand-off between SML and the field |
| `sml_events.py` | Its MQTT subscriptions and publishes, the roster from `track/signalmast`, its answers to `sml_mode` and `sml_claim`, and to an SML dest Enabled change |
| `sml_quit.py` | Its quit release: Hold, Unheld, `sml_mode` disabled, then the pairs off |
| `sml_ui.py` | Its main-window SML button and the stored-Enabled warning popup |
| `check_hart_phase02.py` | Acceptance checks for hart phases 0–2 (in `tools/check.sh`) |
| `generate_nx_pairs.py` | List Entry/Exit pairs for manual JMRI add (parked with NX; see `layouts/hart/parked/README.md`) |

## Documentation

Pipelines: [`wiki/pipelines/README.md`](../wiki/pipelines/README.md) · agent notes: [`wiki/home.md`](../wiki/home.md)
