# Pipeline 2 — Public names + comments

Apply the live naming grammar to JMRI beans and generated panels. Hardware MQTT `systemName`s stay frozen (`M2T*`, `M2S*`, `IH*`, `IS*:`, `ISNX:*`). LCC turnout aliases `MTT100`–`MTT119` are required twins (userName `DCC Switch N`, comment is MQTT minus `DCC: NNN`, same FB sensors). `audit_panel_contracts.py --strict` fails if any MQTT DCC turnout lacks its MTT twin. Do not delete MTT* as leftovers.

**Status:** Live. [ADR-005](../decisions/ADR-005-public-equipment-names.md).

## Inputs

- The device master: [`devices_field.csv`](../../jmri/layouts/hart/data/devices_field.csv) (hand-kept) and [`devices_generated.csv`](../../jmri/layouts/hart/data/devices_generated.csv) (generator output), read as one view by `hartlib.devices`. A public name is a row's `user_name`. The old public name map and the two device maps are gone (ADR-029)
- Device-map comments (node / OU / ports / `DCC: NNN`)

## Outputs

- `userName` on turnouts, sensors, blocks, heads, masts in `jmri/layouts/hart/output/tables.xml` and hart `output/`
- Occupancy comments `Block n-n`; wiring comments on hardware beans
- Names baked into USS / CATS **after regenerate**, not by string-replace of generated XML

## Run

```bash
export JMRI_LAYOUT=hart
PYTHONPATH=tools/hartlib/src python3 -m hartlib.devices check   # after an edit of the device master
python3 jmri/layouts/hart/scripts/check_bean_comments.py
python3 jmri/layouts/hart/scripts/audit_panel_contracts.py --strict
```

Beans **with a generator** (USS diagram, CATS Masters, signal heads): change the script or CSV, then regenerate those pipelines. Do not search-replace their output.

Writable tables: `jmri/layouts/hart/output/tables.xml`.

## Renaming

A rename is an edit of the row's `user_name` in the device master: in `devices_field.csv` for a hand-kept row, in its builder's input for a row `devices_generated.csv` holds (and of the bean in `tables.xml` while PanelPro owns that file), then `python3 -m hartlib.devices check` and the builds that bind the name. No old-name history is kept (ADR-029); `tools/audit/check_name_copies.py` finds hand-kept copies of Mast and OS names that are no longer current.

## Do not

- Change MQTT topics or `systemName`s
- Put leftover Switch 100–119 in public names (DCC address stays in turnout **comments**)
- Add one-off deletes to `cleanup_uss_ctc_leftovers.py` as a forever list
