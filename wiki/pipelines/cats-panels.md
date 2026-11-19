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

## Diagnosing a panel

`python3 cats/scripts/analyze_cats_edges.py <panel.xml>...` reports how each `SEC_EDGE` joint is typed (block, switchpoints or plain). It is read-only.

## Do not

- Run CATS CTC and USS CTC (or Dispatcher System from inside CATS) at the same time
- Store JMRI tables from a CATS session
- Hand-edit `HART_CTC.xml` or `HART_ABS.xml`; the next build replaces them (`build_cats_panel.py --check` fails on any edit)
- Command field turnouts / publish `track/cmd` from launch or paint-fix scripts
