# Pipeline 8 — Wiring documentation

Refresh LCOS inventory workbooks and the per-node PowerPoint from hart CSVs.

**Status:** Live in [`docs/wiring/`](../../docs/wiring/), the only copy (the Desktop bench copy was retired 2026-11-09).

## Inputs

- `jmri/layouts/hart/data/wiring.csv`: the physical wiring source (`hartlib.wiring`; owner, 2026-11-20). Staging as JMRI has it wired, and the main and upper devices placed so far
- The device master (`devices_field.csv` + `devices_generated.csv`, read by `hartlib.devices`): every level's devices with their wiring text (`build_device_map.py` writes staging's from `wiring.csv`, main and upper's by its rule: a proposal in `devices_generated.csv`, worked out from the LCOS node rules on every build and never written to `wiring.csv`)
- `jmri/layouts/hart/data/schematic/lcos_nodes.csv`: every node
- `jmri/layouts/hart/output/signal_head_plan.csv`: the Digicon masts, written by `build_hart_signal_heads.py --wiring-only` from `wiring.csv`'s heads (a `make panels` step, `head-plan`)
- `docs/wiring/lcos/lcos_signal_logic.csv` → `docs/wiring/lcos/lcos_signal_manager_config_plan.xlsx` (Main/Diverged + OR)

## Outputs

- `docs/wiring/LCOS_Layout_Inventory_v86.xlsx`: every level, a view written from scratch
- `docs/wiring/Wiring_Schematic.pptx`
- `docs/wiring/lcos/lcos_signal_manager_config_plan.xlsx`
- `www/data/wiring-inventory.json`: the website's viewer

History, frozen (no generator): `signals_asbuilt_abs_v2.xlsx`. `LCOS_Layout_Inventory_v85.xlsx` and `signals_split_v8.xlsx` were archived on 2026-11-25 (`archive/docs/wiring/`). The v84 import and the refresh that turned it into v85 are in `archive/` (2026-11-20).

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

`docs/wiring/` is the only copy (the Desktop pack was retired, ADR-007). For Signal Manager punching, use `docs/wiring/lcos/lcos_signal_manager_config_plan.xlsx`. Detail: [`docs/wiring/README.md`](../../docs/wiring/README.md).

## Do not

- Write main or upper wiring into `wiring.csv` any way but `make wiring-freeze` (it copies a control point's proposal in as wired rows, noted "frozen from the device map's rule (CP n, date)"). Data flows one way: rules, proposal, freeze, `wiring.csv`, device map; for a frozen control point `build_device_map.py` reads `wiring.csv` through `hartlib.wiring.held` and proposes nothing (it stops on a device the rule would still give one). `tools/wiring/check_wiring_frozen.py` (in `check.sh`) fails on a main or upper row wired with no freeze note, a frozen control point with a row not wired, or text not in the freeze's format
- Edit v86 or the wiring cells of the device master by hand: change `wiring.csv`, then rebuild
- Put packed MQTT on helix **D5**
