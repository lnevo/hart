# Pipeline 2 — Public names + comments

Apply the live naming grammar to JMRI beans and generated panels. Hardware MQTT `systemName`s stay frozen (`M2T*`, `M2S*`, `IH*`, `IS*:`, `ISNX:*`).

**Status:** Live. [ADR-005](../decisions/ADR-005-public-equipment-names.md).

## Inputs

- [`jmri/layouts/hart/data/public_name_map.csv`](../../jmri/layouts/hart/data/public_name_map.csv)
- Device-map comments (node / OU / ports / `DCC: NNN`)

## Outputs

- `userName` on turnouts, sensors, blocks, heads, masts in `tables/new_tables.xml` and hart `output/`
- Occupancy comments `Block n-n`; wiring comments on hardware beans
- Names baked into USS / CATS **after regenerate**, not by string-replace of generated XML

## Run

```bash
export JMRI_LAYOUT=hart
python3 jmri/layouts/hart/scripts/apply_public_names.py          # dry-run first
python3 jmri/layouts/hart/scripts/apply_public_names.py --apply
python3 jmri/layouts/hart/scripts/refresh_bean_comments.py --apply
python3 jmri/layouts/hart/scripts/sync_public_name_map.py
python3 jmri/layouts/hart/scripts/audit_panel_contracts.py --strict
```

Beans **with a generator** (USS diagram, CATS Masters, signal heads): change the script or CSV, then regenerate those pipelines. Do not search-replace their output.

Writable tables only: `tables/new_tables.xml` (never `tables/tables.xml`).

## Do not

- Change MQTT topics or `systemName`s
- Put leftover Switch 100–119 in public names (DCC address stays in turnout **comments**)
- Add one-off deletes to `cleanup_uss_ctc_leftovers.py` as a forever list
