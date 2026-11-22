# Pipeline 7 — Dispatcher System graph

**Parked.** Parked since the helix-join release (November 2026): not in the active panel; data kept in `jmri/layouts/hart/parked/`. Everything below describes the pipeline as it runs once unparked.

CreateTransits (Stage 1) in PanelPro builds sections, transits, and traininfo so auto-dispatch can run station to station.

Printed SoR: [`jmri/layouts/hart/dispatcher/JMRI_Dispatcher_System.pdf`](../../jmri/layouts/hart/dispatcher/JMRI_Dispatcher_System.pdf) (same as [JMRI help Stage 1](https://www.jmri.org/help/en/html/scripthelp/DispatcherSystem/DispatcherSystem.shtml#_Toc194074958)).

**Status:** 2026-11-12 — stock Stage 1, 12 stations. **49 / 107 / 187 / 374**. East Lead and K-1 rear masts 36L / 40RB on hidden throats. No CreateTransits overlay. EH exits are 12R/10RA/10RB (were 11L/9LA/9LB); Barn at Switch 13 is 14R (was 13R); Brick-Plane ends are 2R/6R.

## Inputs

- Hidden virtual masts + throat blocks ([`DISPATCHER_LAYOUT_HOOPS.md`](../../jmri/layouts/hart/parked/DISPATCHER_LAYOUT_HOOPS.md))
- Block comments with `stop` on station bodies (throats: “not a station”, never “not a stop”) (parked with the stations topic since 2026-11-22: no block carries `stop`; [`docs/parked/UNPARK.md`](../../docs/parked/UNPARK.md))
- Roster speed profiles (synthetic today — pipeline 11)

## Outputs

- Sections / transits / traininfo in the tables bundle
- Logix **Run Dispatcher** (`IX:DSLX:1C1`) runs stock `program:jython/DispatcherSystem/Startup.py`

## Repair stale TrainInfo

`jmri/layouts/hart/scripts/run_panelpro_traininfo_repair.sh` loads HART in PanelPro on the Mac, repairs stale generated TrainInfo bindings, then exits. Do not run it with PanelPro or CATS open.

## Run

1. **PanelPro only** (not CATS). Load hart tables.
2. Prefer the Mac generator: `jmri/layouts/hart/scripts/run_panelpro_stage1.sh` (auto-Yes shared-sensor). Do not click Stage 1 on the Pi.
3. If Dispatcher asks to rebuild because traininfo names are stale, try
   `python3 jmri/layouts/hart/parked/retarget_dispatcher_traininfo_transits.py`
   first.
4. After Stage 1, `run_panelpro_stage1.sh` runs the repairs itself (see `jmri/layouts/hart/parked/DISPATCHER_LAYOUT_HOOPS.md`).
5. Stage 1 Store writes BlockContentsIcons at level 0. The launcher runs
   `jmri/layouts/hart/parked/polish_hart_layout_editor.py --reference <tables before Stage 1>` so labels
   go back to their reference spots (above the rail).
6. Post-scripts:

```bash
python3 jmri/layouts/hart/parked/retarget_dispatcher_traininfo_transits.py
python3 jmri/layouts/hart/scripts/fix_traininfo_detection.py
python3 jmri/layouts/hart/scripts/reconcile_dispatcher_stations.py
```

Operator: [`jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md`](../../jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md).

## Do not

- Stage 1 or Store tables from CATS
- Patch or wrap Dispatcher System / JMRI. Fix `jmri/layouts/hart/output/tables.xml` so stock Discover and Stage 1 succeed.
- `from __future__ import print_function` in `preference:jython/` (breaks stock Dispatcher System)
- Hold a WiThrottle on the same DCC address while AutoActiveTrain owns it
