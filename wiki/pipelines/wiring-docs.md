# Pipeline 8 — Wiring documentation

Refresh LCOS inventory workbooks and the per-node PowerPoint from hart CSVs.

**Status:** Live in [`docs/wiring/`](../../docs/wiring/), the only copy (the Desktop bench copy was retired 2026-11-09).

## Inputs

- `cats/data/occupancy_bindings.csv`
- `docs/wiring/signals/signal_wiring.csv`, `signal_head_plan.csv`, `signal_mast_plan.csv`
- `docs/wiring/lcos/lcos_signal_logic.csv` → `docs/wiring/lcos/lcos_signal_manager_config_plan.xlsx` (Main/Diverged + OR)
- `docs/wiring/imported/` snapshots
- `devices.csv` (the name map: proposed strings)

## Outputs

- `docs/wiring/LCOS_Layout_Inventory_v85.xlsx` (staging)
- `docs/wiring/LCOS_Layout_Inventory_v86.xlsx` (v85 plus the main and upper levels from `devices.csv`)
- `docs/wiring/signals_asbuilt_abs_v2.xlsx`
- `docs/wiring/signals_split_v8.xlsx` (frozen RGB plan + notes)
- `docs/wiring/Wiring_Schematic.pptx`
- `docs/wiring/lcos/lcos_signal_manager_config_plan.xlsx`

## Run

```bash
python3 jmri/layouts/hart/scripts/build_hart_signal_heads.py --wiring-only
python3 tools/wiring/build_lcos_signal_manager_plan.py
python3 tools/wiring/refresh_wiring_docs.py
python3 tools/schematic/build_device_map.py
python3 tools/wiring/add_main_upper_levels.py
python3 tools/wiring/create_wiring_schematic_ppt.py
python3 www/scripts/build_wiring_json.py   # site viewer; signal splits keep v85 pins (--splits-inventory); tools/check.sh fails while it is stale
```

`refresh_wiring_docs.py` is the entry point; its rename tables and sheet steps live in the `refresh_wiring_*.py` modules beside it, and its tests are `tools/audit/tests/test_refresh_wiring_docs.py`.

Copy the three workbooks **and** the pptx back to the Desktop pack after XML apply so the bench matches live beans. Also copy `docs/wiring/lcos/lcos_signal_manager_config_plan.xlsx` if you are punching Signal Manager. Detail: [`docs/wiring/README.md`](../../docs/wiring/README.md).

## Do not

- Treat Desktop `ARCHIVE/` one-off Python as the live generator (git `tools/wiring/` is)
- Refresh Desktop before JMRI XML is applied if the pack must match beans
- Put packed MQTT on helix **D5**
