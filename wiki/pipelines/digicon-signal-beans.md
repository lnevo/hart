# Pipeline 3 — Digicon signal beans

Build JMRI Virtual heads + SignalHeadSignalMasts from the wiring catalog. Appearances are stock **Basic** (`two-searchlight` / `one-low`). Flashing aspects are disabled on the mast. Layout Editor icons are `discriminated` at scale 1.0.

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
python3 jmri/layouts/hart/scripts/build_hart_signal_heads.py
```

Facing / SML chaining: [`cats/docs/SIGNAL_FACING.md`](../../cats/docs/SIGNAL_FACING.md). Decision: [`../decisions/ADR-011-co-1980-signals.md`](../decisions/ADR-006-co-1980-signals.md).

MQTT SET uses packed topics `track/signalhead/<digits>` and field status `track/signalmast/<digits>` — not an include list. Live roster is LCOS mast traffic.

## Do not

- Use stock `SL-2-high-abs` for two-lamp Digicon homes (SML pins at Stop)
- Mix C&O-1980 homes with AAR-1946 dwarfs
- Put `IH` in the MQTT topic leaf
- Store tables from a CATS session
