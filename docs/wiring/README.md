# HART LCOS wiring documentation

Git copy of the Desktop `HART/Wiring Documentation` package, refreshed against current public names and Digicon searchlight heads.

Desktop originals stay at `~/Desktop/HART/Wiring Documentation/`. That tree is **not** git — it has a Python venv and an `ARCHIVE/` of every inventory bump. Root `.gitignore` still ignores a repo-root `Wiring Documentation/` folder so that checkout is not committed by accident.

## Current files

| File | Role |
|------|------|
| [`LCOS_Layout_Inventory_v85.xlsx`](LCOS_Layout_Inventory_v85.xlsx) | LCOS nodes, DNOU8/DNIN8, block sensors, turnout summary. **DigiconSignals** sheet is generated from `cats/data/signal_wiring.csv`. |
| [`Wiring_Schematic.pptx`](Wiring_Schematic.pptx) | One slide per client node, regenerated from v85. |
| [`signals_asbuilt_abs_v2.xlsx`](signals_asbuilt_abs_v2.xlsx) | Live lower-deck Digicon ABS matrix (100L, 117LA, 114LA, …). |
| [`signals_split_v8.xlsx`](signals_split_v8.xlsx) | Frozen Nov 2025 **planned RGB** matrix (`S1-1`…`S6-15`). Upper deck still uses this plan. Do not rename those IDs to Digicon 11x names. |
| [`imported/`](imported/) | Unmodified Desktop snapshots (v84, asbuilt v1, split v8, v84 changelog). |

CSV source of truth for Digicon ports: [`cats/data/signal_wiring.csv`](../../cats/data/signal_wiring.csv). Public block names: [`occupancy_bindings.csv`](../../cats/data/occupancy_bindings.csv) / [ADR-005](../../wiki/decisions/ADR-005-public-equipment-names.md).

**Next refresh (not in live CSVs yet):** packed MQTT node = radio Address. Princess heads on **C1** (radio 1), never **D1** (radio 5, DCC). East End on **C3** (radio 2). Barn on **C5** (radio 13). Princess overflow + intermediates **2035/2036** on **C7** (radio 11). One 3-pin `STOP/APPROACH/CLEAR` head per mast.

**102LA** is a 1-head dwarf on `C4-OU2-3` / `IH434`. `C4-OU2-4` is an unused packed hole (old 102LA Bottom / IH435); do not reuse it for 101RA. Live overlay still lists 2035/2036 on invented D1 ports — that goes away on refresh. `signals_split_v8.xlsx` stays the frozen RGB plan.

Copy the three current workbooks **and** `Wiring_Schematic.pptx` back to `~/Desktop/HART/Wiring Documentation/` after a refresh (and after XML apply) so the bench copy matches git.

## Refresh

```bash
python3 docs/wiring/scripts/refresh_wiring_docs.py
# needs python-pptx (Desktop wiring venv is fine):
python3 docs/wiring/scripts/create_wiring_schematic_ppt.py
```

Copy `LCOS_Layout_Inventory_v85.xlsx`, `signals_asbuilt_abs_v2.xlsx`, `signals_split_v8.xlsx`, and `Wiring_Schematic.pptx` to `~/Desktop/HART/Wiring Documentation/`. Do not refresh Desktop until JMRI XML is applied so the bench pack matches live beans.

## What v85 changed vs Desktop v84

- Lower-deck **BlockSensors** names follow the panel: Scale, Barn, S-1…S-5, W-1/W-2, EH-1…EH-3, OS 100… (MQTT `Block n-n` stays in Notes).
- **DNOU8** ports listed in `signal_wiring.csv` are overlayed as searchlight heads (replacing planned RGB `S3-6 G` etc. on those ports). Previous RGB label is kept in Notes.
- **D1-OU2/OU3** Princess rows were a mistaken overlay (D1 is DCC radio 5). Next refresh puts Princess on C1 radio 1 and must not recreate D1 signal boards.
- Upper-deck RGB (`S4-*` / `S5-*` / `S6-*`) left as planned.
- C# vs radio address is unchanged from v84b: client IDs are enclosure groups; MQTT packed IDs use the radio address (`C# ≠ node`). **Queued:** rename Node IDs to the radio Address so enclosure labels match packed MQTT (see `wiki/STATUS.md`).
