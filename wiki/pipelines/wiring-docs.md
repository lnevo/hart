# Pipeline 8 — Wiring documentation

Refresh LCOS inventory workbooks and the per-node PowerPoint from hart CSVs.

**Status:** Live. Git copy: [`docs/wiring/`](../../docs/wiring/). Bench copy: `~/Desktop/HART/Wiring Documentation/` (not git).

## Inputs

- `cats/data/occupancy_bindings.csv`
- `cats/data/signal_wiring.csv`, `signal_head_plan.csv`, `signal_mast_plan.csv`
- `docs/wiring/imported/` snapshots
- `public_name_map.csv` (proposed strings)

## Outputs

- `docs/wiring/LCOS_Layout_Inventory_v85.xlsx`
- `docs/wiring/signals_asbuilt_abs_v2.xlsx`
- `docs/wiring/signals_split_v8.xlsx` (frozen RGB plan + notes)
- `docs/wiring/Wiring_Schematic.pptx`

## Run

```bash
python3 docs/wiring/scripts/refresh_wiring_docs.py
python3 docs/wiring/scripts/create_wiring_schematic_ppt.py
```

Copy the three workbooks **and** the pptx back to the Desktop pack after XML apply so the bench matches live beans. Detail: [`docs/wiring/README.md`](../../docs/wiring/README.md).

## Do not

- Treat Desktop `ARCHIVE/` one-off Python as the live generator (git `docs/wiring/scripts/` is)
- Refresh Desktop before JMRI XML is applied if the pack must match beans
- Put packed MQTT on helix **D5**
