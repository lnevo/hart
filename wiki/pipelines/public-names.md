# Pipeline 2 — Public names + comments

Apply the live naming grammar to JMRI beans and generated panels. Hardware MQTT `systemName`s stay frozen (`M2T*`, `M2S*`, `IH*`, `IS*:`, `ISNX:*`). LCC turnout aliases `MTT100`–`MTT119` are required twins (userName `DCC Switch N`, comment is MQTT minus `DCC: NNN`, same FB sensors). `audit_panel_contracts.py --strict` fails if any MQTT DCC turnout lacks its MTT twin. Do not delete MTT* as leftovers.

**Status:** Live. [ADR-005](../decisions/ADR-005-public-equipment-names.md).

## Inputs

- [`jmri/layouts/hart/data/devices.csv`](../../jmri/layouts/hart/data/devices.csv): the device master. A public name is a row's `user_name`. `public_name_map.csv` and the two device maps are generated from it
- Device-map comments (node / OU / ports / `DCC: NNN`)

## Outputs

- `userName` on turnouts, sensors, blocks, heads, masts in `jmri/layouts/hart/output/tables.xml` and hart `output/`
- Occupancy comments `Block n-n`; wiring comments on hardware beans
- Names baked into USS / CATS **after regenerate**, not by string-replace of generated XML

## Run

```bash
export JMRI_LAYOUT=hart
PYTHONPATH=tools/hartlib/src python3 -m hartlib.devices regenerate   # after an edit to devices.csv
python3 jmri/layouts/hart/scripts/refresh_bean_comments.py
python3 jmri/layouts/hart/scripts/audit_panel_contracts.py --strict
```

Beans **with a generator** (USS diagram, CATS Masters, signal heads): change the script or CSV, then regenerate those pipelines. Do not search-replace their output.

Writable tables: `jmri/layouts/hart/output/tables.xml`.

## Renaming

A rename is an edit of the row's `user_name` in `devices.csv` (and of the bean in `tables.xml` while PanelPro owns that file), then `python3 -m hartlib.devices regenerate` and the builds that bind the name. No old-name history is kept (ADR-029); `tools/audit/check_name_copies.py` finds hand-kept copies of Mast and OS names that are no longer current.

## Do not

- Change MQTT topics or `systemName`s
- Put leftover Switch 100–119 in public names (DCC address stays in turnout **comments**)
- Add one-off deletes to `cleanup_uss_ctc_leftovers.py` as a forever list
