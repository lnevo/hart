# Pipeline 8 — Wiring documentation

Refresh LCOS inventory workbooks and the per-node PowerPoint from hart CSVs.

**Status:** Live in [`docs/wiring/`](../../docs/wiring/), the only copy (the Desktop bench copy was retired 2026-11-09).

## Inputs

- `jmri/layouts/hart/data/wiring.csv`: the physical wiring source (`hartlib.wiring`; owner, 2026-11-20). Staging as JMRI has it wired, and the main and upper devices placed so far
- `jmri/layouts/hart/data/devices.csv`: every level's devices with their wiring text (`build_device_map.py` writes staging's from `wiring.csv`, main and upper's by its rule)
- `jmri/layouts/hart/data/schematic/lcos_nodes.csv`: every node
- `docs/wiring/signals/signal_head_plan.csv`, `signal_mast_plan.csv`: the Digicon masts, written by `build_hart_signal_heads.py --wiring-only` from `wiring.csv`'s heads
- `docs/wiring/lcos/lcos_signal_logic.csv` → `docs/wiring/lcos/lcos_signal_manager_config_plan.xlsx` (Main/Diverged + OR)

## Outputs

- `docs/wiring/LCOS_Layout_Inventory_v86.xlsx`: every level, a view written from scratch
- `docs/wiring/Wiring_Schematic.pptx`
- `docs/wiring/lcos/lcos_signal_manager_config_plan.xlsx`
- `www/data/wiring-inventory.json`: the website's viewer

History, frozen (no generator): `LCOS_Layout_Inventory_v85.xlsx`, `signals_asbuilt_abs_v2.xlsx`, `signals_split_v8.xlsx`. The v84 import and the refresh that turned it into v85 are in `archive/` (2026-11-20).

## Run

```bash
python3 jmri/layouts/hart/scripts/build_hart_signal_heads.py --wiring-only
python3 tools/wiring/build_lcos_signal_manager_plan.py
python3 tools/schematic/build_device_map.py
python3 tools/wiring/write_inventory.py
make wiring-freeze CP="CP 123"              # once a main or upper control point is wired: its wiring becomes static
python3 tools/wiring/create_wiring_schematic_ppt.py
python3 www/scripts/build_wiring_json.py   # site viewer; signal splits keep v85 pins (--splits-inventory); tools/check.sh fails while it is stale
```

Copy v86 **and** the pptx back to the Desktop pack after XML apply so the bench matches live beans. Also copy `docs/wiring/lcos/lcos_signal_manager_config_plan.xlsx` if you are punching Signal Manager. Detail: [`docs/wiring/README.md`](../../docs/wiring/README.md).

## Do not

- Treat Desktop `ARCHIVE/` one-off Python as the live generator (git `tools/wiring/` is)
- Refresh Desktop before JMRI XML is applied if the pack must match beans
- Put packed MQTT on helix **D5**
