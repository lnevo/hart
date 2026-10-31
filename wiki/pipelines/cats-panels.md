# Pipeline 5 — CATS Digicon panels

Designer save → `wire_digicon.py` → the CATS CTC and CATS ABS desks.

**Status:** Live desks are **CATS CTC** and **CATS ABS**. [ADR-004](../decisions/ADR-004-cats-ctc.md).

## Inputs

- `cats/panels/HART_Digicon.xml` (Designer save; the only panel to edit)
- Device CSVs from `python3 jmri/scripts/export_hart_devices_for_cats.py`

## Outputs

| File | Role |
|------|------|
| `cats/panels/HART_CTC.xml` | Live CTC — routes on; signals HOLD_ONLY; SML owns aspects |
| `cats/panels/HART_ABS.xml` | Live ABS — paints SML; HOLD_ONLY |

## Run

```bash
python3 cats/scripts/wire_digicon.py
python3 cats/scripts/validate_cats_panel.py
./cats/scripts/launch_cats.sh
```

System picture: [`docs/ctc/HART_DIGICON_SYSTEM.md`](../../docs/ctc/HART_DIGICON_SYSTEM.md). Operator: [`docs/ctc/DISPATCHER_GUIDE_CTC.md`](../../docs/ctc/DISPATCHER_GUIDE_CTC.md).

## Do not

- Run CATS CTC and USS CTC (or Dispatcher System from inside CATS) at the same time
- Store JMRI tables from a CATS session
- Hand-edit `HART_CTC.xml` or `HART_ABS.xml`; the next build replaces them
- Command field turnouts / publish `track/cmd` from launch or paint-fix scripts
