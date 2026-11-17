# Pipeline 6 — USS CTC machine

Generate the USS track diagram and CTC table data from a Python plan (Quaker Valley–style icons).

**Status:** Parked. Parked since the helix-join release (November 2026): not in the active panel; data kept in `jmri/layouts/hart/parked/`. When unparked it is an alternate desk, never run with CATS CTC. The CATS desks stay live.

## Inputs

- `jmri/layouts/hart/scripts/gen_ctc_track_plan.py` (`SIGNALS`, drawing)
- Switch facts (lever columns, points dots): [switch-facts.md](switch-facts.md)
- Icons in `jmri/layouts/hart/ctc/icons/` (copied into JMRI user-files on regen/deploy)

## Outputs

- `jmri/layouts/hart/ctc/GUIObjects.xml`
- CTC beans in `jmri/layouts/hart/output/tables.xml` (when the generator writes tables)
- Optional preview PNG under `media/screenshots/master4/`

## Run

```bash
python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py
python3 jmri/layouts/hart/scripts/gen_ctc_track_plan.py --preview media/screenshots/master4/uss_ctc_preview.png
python3 jmri/layouts/hart/scripts/ctc_logic_smoke.py
```

Operator: [`jmri/layouts/hart/ctc/DISPATCHER_GUIDE.md`](../../jmri/layouts/hart/ctc/DISPATCHER_GUIDE.md). Schematic notes: [`DIGICON_SCHEMATIC.md`](../DIGICON_SCHEMATIC.md).

Change public names in the **generator**, then regenerate (pipeline 2).

## Do not

- Run USS CTC and CATS CTC together
- String-replace generated `GUIObjects.xml` for a rename
- Treat preview-only versions as deployed until `sync_hart_package.sh` ran
