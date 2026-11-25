# Pipeline 5 — CATS Digicon panels

Schematic → `tools/schematic/build_cats_panel.py` → the CATS CTC and CATS ABS desks (all three levels; main and upper dark, DTC).

**Status:** Live desks are **CATS CTC** and **CATS ABS**, generated since the CATS cut-over (owner approved in real CATS on 2026-11-15; [ADR-023](../decisions/ADR-023-generated-outputs-side-by-side.md), [ADR-004](../decisions/ADR-004-cats-ctc.md)). The hand-wired desks `wire_digicon.py` built from `HART_Digicon.xml` are history, in git at commit `42192d9c`, before the CATS cut-over (`git show 42192d9c:cats/panels/HART_CTC.xml`).

## Inputs

- The solved schematic (as `tools/schematic/publish_draft.py`), the device map for main and upper
- Switch facts (closed and thrown legs, inversion): [switch-facts.md](switch-facts.md); occupancy bindings, mast templates
- `cats/data/generated_desk_header.xml` (fonts, templates, stores, plate; frozen from the hand-wired desk)

## Outputs

| File | Role |
|------|------|
| `cats/panels/HART_CTC.xml` | Live CTC — routes on; signals HOLD_ONLY; SML owns aspects |
| `cats/panels/HART_ABS.xml` | Live ABS — paints SML; HOLD_ONLY |
| `cats/panels/HART_CTC.bindings.json` | What each switch, block and mast binds to (written from the facts) |

## Run

```bash
make desks        # python3 tools/schematic/build_cats_panel.py, then validate_cats_panel.py
./cats/scripts/launch_cats.sh
```

System picture: [`docs/ctc/HART_DIGICON_SYSTEM.md`](../../docs/ctc/HART_DIGICON_SYSTEM.md). Operator: [`docs/ctc/DISPATCHER_GUIDE_CTC.md`](../../docs/ctc/DISPATCHER_GUIDE_CTC.md).

## Desk discipline

Owner, 2026-11-17: signals run ABS unless CATS holds and releases them. On the CTC desk (`HART_CTC.xml`) main and upper blocks are CTC like staging, so a route set from staging up the helix stops at the first main or upper signal (136RA main, 136RB upper); the ABS twin (`HART_ABS.xml`) is all ABS. Ask before any DTC. Switch 225 is one desk block per corner (OS Switch 225a to 225d) plus a middle block with no detector that stays dark; the 107 Loop is two desk blocks. The helix tracks 135-H1 and 135-H2 keep their own desk blocks and detectors. Main and upper detection comes with the into-service work.

## Diagnosing a panel

`python3 cats/scripts/cats_inspect.py` reads a panel and writes nothing:

- `edges <panel.xml>...` reports how each `SEC_EDGE` joint is typed (block, switchpoints or plain).
- `grid <panel.xml>...` lists every track cell with its tracks and edge kinds.
- `trace <panel.xml>` lists every wired plant with its OS block and the block each leg leads to; `trace <panel.xml> X Y LEG` follows one leg. It uses `digicon_trace.py`, as the desk build does.

## Do not

- Run CATS CTC and USS CTC (or Dispatcher System from inside CATS) at the same time
- Store JMRI tables from a CATS session
- Hand-edit `HART_CTC.xml` or `HART_ABS.xml`; the next build replaces them (`build_cats_panel.py --check` fails on any edit)
- Command field turnouts / publish `track/cmd` from launch or paint-fix scripts
