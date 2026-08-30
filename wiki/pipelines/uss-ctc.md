# Pipeline 6 — USS CTC machine

Generate the USS track diagram and CTC table data from a Python plan (Quaker Valley–style icons).

**Status:** Live alternate desk. Never with CATS CTC.

## Inputs

- `jmri/layouts/hart/scripts/gen_ctc_track_plan.py` (`SIGNALS`, plant columns)
- Icons in `jmri/layouts/hart/ctc/icons/` (copied into JMRI user-files on regen/deploy)

## Outputs

- `jmri/layouts/hart/ctc/GUIObjects.xml`
- CTC beans in `tables/new_tables.xml` (when the generator writes tables)
- Optional preview PNG under `cats/screenshots/master4/`

## Run

```bash
python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py
python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py --preview cats/screenshots/master4/uss_ctc_preview.png
python3 jmri/layouts/hart/scripts/ctc_logic_smoke.py
```

Operator: [`jmri/layouts/hart/ctc/DISPATCHER_GUIDE.md`](../../jmri/layouts/hart/ctc/DISPATCHER_GUIDE.md). Schematic notes: [`MASTER4_SCHEMATIC.md`](../MASTER4_SCHEMATIC.md).

Change public names in the **generator**, then regenerate (pipeline 2).

## Do not

- Run USS CTC and CATS CTC together
- String-replace generated `GUIObjects.xml` for a rename
- Treat preview-only versions as deployed until `sync_hart_package.sh` ran
