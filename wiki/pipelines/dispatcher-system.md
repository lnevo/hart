# Pipeline 7 — Dispatcher System graph

CreateTransits (Stage 1) in PanelPro builds sections, transits, and traininfo so auto-dispatch can run station to station.

Printed SoR: [`jmri/layouts/hart/dispatcher/JMRI_Dispatcher_System.pdf`](../../jmri/layouts/hart/dispatcher/JMRI_Dispatcher_System.pdf) (same as [JMRI help Stage 1](https://www.jmri.org/help/en/html/scripthelp/DispatcherSystem/DispatcherSystem.shtml#_Toc194074958)).

**Status:** 2026-09-01 — stock Stage 1. **45 / 103 / 746 / 1548**. No CreateTransits overlay. EH exits are 11L/9LA/9LB.

## Inputs

- Hidden virtual masts + throat blocks ([`DISPATCHER_LAYOUT_HOOPS.md`](../DISPATCHER_LAYOUT_HOOPS.md))
- Block comments with `stop` on station bodies (throats: “not a station”, never “not a stop”)
- Roster speed profiles (synthetic today — pipeline 11)

## Outputs

- Sections / transits / traininfo in the tables bundle
- Logix **Run Dispatcher** (`IX:DSLX:1C1`) runs stock `program:jython/DispatcherSystem/Startup.py`

## Run

1. **PanelPro only** (not CATS). Load hart tables.
2. Prefer the Mac generator: `jmri/layouts/hart/scripts/run_panelpro_stage1.sh` (auto-Yes shared-sensor). Do not click Stage 1 on the Pi.
3. If Dispatcher asks to rebuild because traininfo names are stale, try
   `python3 jmri/layouts/hart/scripts/retarget_dispatcher_traininfo_transits.py`
   first.
4. After Stage 1, re-add manual Princess SML pairs only if Discover still missed them (pipeline 4).
5. Post-scripts:

```bash
python3 jmri/layouts/hart/scripts/retarget_dispatcher_traininfo_transits.py
python3 jmri/layouts/hart/scripts/fix_traininfo_detection.py
python3 jmri/layouts/hart/scripts/reconcile_dispatcher_stations.py
```

Operator: [`jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md`](../../jmri/layouts/hart/dispatcher/DISPATCHER_GUIDE.md).

Stock facing invert is [JMRI#15407](https://github.com/JMRI/JMRI/issues/15407). If a through-station loco runs the wrong way, use **Modify Dispatcher System → Change Dir**. Do not add a HART overlay.

## Do not

- Stage 1 or Store tables from CATS
- Patch or wrap Dispatcher System / JMRI. Fix `tables/new_tables.xml` so stock Discover and Stage 1 succeed.
- `from __future__ import print_function` in `preference:jython/` (breaks stock Dispatcher System)
- Hold a WiThrottle on the same DCC address while AutoActiveTrain owns it
