# Pipeline 10 — LCOS PCBWay BOM

Merge KiCad Interactive BOM HTML with a Mouser cart into a PCBWay-style xlsx.

**Status:** Live in the LCOS repo. Not HART panel XML.

## Inputs

- `pcb-BOM.html` from the Gerber / manufacturing zip (copper files have no BOM)
- Mouser saved-cart `.xls`

## Outputs

- PCBWay BOM workbook (designator, qty, mfr part, footprint, notes)

## Run

From `LCOS_ESP32_MQTT_Client`:

```bash
python3 scripts/build_esp32io_pcbway_bom.py --help
```

Script: `scripts/build_esp32io_pcbway_bom.py`. Gerber copper/mask alone is not enough; use the Interactive BOM HTML from the same archive.
