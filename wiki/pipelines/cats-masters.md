# Pipeline 5 — CATS Digicon Masters

Designer geometry → wired Master XML → HOLD_ONLY CTC and ABS launchers.

**Status:** Live desks are **CATS CTC** and **CATS ABS**. [ADR-004](../decisions/ADR-004-cats-ctc.md).

## Inputs

- `cats/panels/HART_Master.xml` (geometry; rebuild from Master4 via `wire_hart_master4.py --live`)
- Device CSVs from `python3 jmri/scripts/export_hart_devices_for_cats.py`

## Outputs

| File | Role |
|------|------|
| `cats/panels/HART_Master_CTC_hold.xml` | Live CTC — routes on; signals HOLD_ONLY; SML owns aspects |
| `cats/panels/HART_Master_ABS_hold.xml` | Live ABS — paints SML; HOLD_ONLY |

## Run

```bash
python3 cats/scripts/wire_hart_master4.py --live
python3 cats/scripts/build_hart_master_ctc_hold.py
python3 cats/scripts/build_hart_master_abs_hold.py
python3 cats/scripts/polish_hart_master_header.py --panel all
python3 cats/scripts/validate_cats_panel.py
./cats/scripts/launch_cats.sh
```

System picture: [`cats/docs/HART_DIGICON_SYSTEM.md`](../../cats/docs/HART_DIGICON_SYSTEM.md). Operator: [`cats/docs/DISPATCHER_GUIDE_CTC.md`](../../cats/docs/DISPATCHER_GUIDE_CTC.md).

## Do not

- Run CATS CTC and USS CTC (or Dispatcher System from inside CATS) at the same time
- Store JMRI tables from a CATS session
- Treat Gate 1 `HART.xml` as the ops board
- Command field turnouts / publish `track/cmd` from launch or paint-fix scripts
