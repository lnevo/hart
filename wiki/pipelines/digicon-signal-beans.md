# Pipeline 3 — Digicon signal beans

JMRI Virtual heads + SignalHeadSignalMasts live in `tables.xml`; the wiring catalog (CSVs below) is generated from the head plan and must agree with them. Appearances are stock **Basic** (`two-searchlight` / `one-low`). No aspects are disabled (ADR-011). Layout Editor icons are `discriminated` at scale 1.0.

**Status:** Live.

## Inputs

- [`docs/wiring/signals/signal_wiring.csv`](../../docs/wiring/signals/signal_wiring.csv) (3 pins per disc)
- [`docs/wiring/signals/signal_head_plan.csv`](../../docs/wiring/signals/signal_head_plan.csv)
- [`docs/wiring/signals/signal_mast_plan.csv`](../../docs/wiring/signals/signal_mast_plan.csv)

Packed MQTT leaf = radio node × 100 + UID (example: node 4, UID 0 → `432` / `IH432`).

## Outputs

- IH / SHSM beans in tables (Basic `two-searchlight` two-head; `one-low` dwarfs and dispatcher virtuals).

## Run

```bash
python3 jmri/layouts/hart/scripts/build_hart_signal_heads.py --wiring-only
```

Head IH numbers in `tables.xml` follow the wiring plan (packed = radio address × 100 + slot); `tools/audit/check_wiring_crosswalk.py` fails in `./tools/check.sh` when a head on a physical mast differs from `signal_wiring.csv`. The full run (no flag) refuses to rewrite `tables.xml`, because its generated block would drop the virtual masts, IH9990 and the mast comments. Change heads and masts in `tables.xml` directly (PanelPro and CATS closed), then run `--wiring-only` and check that `git diff` shows only what you meant. Interim builds with fewer heads than planned (Mast 6LB) are listed in `FITTED_HEADS` in the script.

Facing / SML chaining: [`docs/ctc/SIGNAL_FACING.md`](../../docs/ctc/SIGNAL_FACING.md). Decision: [`ADR-006-co-1980-signals.md`](../decisions/ADR-006-co-1980-signals.md).

MQTT SET uses packed topics `track/signalhead/<digits>` and field status `track/signalmast/<digits>` — not an include list. Live roster is LCOS mast traffic.

## Do not

- Use stock `SL-2-high-abs` for two-lamp Digicon homes (SML pins at Stop)
- Mix C&O-1980 homes with AAR-1946 dwarfs
- Put `IH` in the MQTT topic leaf
- Store tables from a CATS session
