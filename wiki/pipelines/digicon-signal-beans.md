# Pipeline 3 — Digicon signal beans

Build JMRI Virtual heads + SignalHeadSignalMasts from the wiring catalog. Appearances are stock **C&O-1980** (`CO-33-hi` / `CO-3-dwarf`) plus a user-files overlay for USS CTC icons.

**Status:** Live.

## Inputs

- [`cats/data/signal_wiring.csv`](../../cats/data/signal_wiring.csv) (3 pins per disc)
- [`cats/data/signal_head_plan.csv`](../../cats/data/signal_head_plan.csv)
- [`cats/data/signal_mast_plan.csv`](../../cats/data/signal_mast_plan.csv)

Packed MQTT leaf = radio node × 100 + UID (example: node 4, UID 0 → `432` / `IH432`).

## Outputs

- IH / SHSM beans in tables (C&O-1980 `CO-33-hi` two-head; `CO-3-dwarf` dwarfs and dispatcher virtuals)
- [`cats/resources/signals/C&O-1980/`](../../cats/resources/signals/C&O-1980/) (deployed by `sync_hart_package.sh`)

## Run

```bash
python3 cats/scripts/build_hart_signal_heads.py
```

Facing / SML chaining: [`cats/docs/SIGNAL_FACING.md`](../../cats/docs/SIGNAL_FACING.md). Decision: [`../decisions/ADR-006-co-1980-signals.md`](../decisions/ADR-006-co-1980-signals.md).

MQTT SET uses packed topics `track/signalhead/<digits>` and field status `track/signalmast/<digits>` — not an include list. Live roster is LCOS mast traffic.

## Do not

- Use stock `SL-2-high-abs` for two-lamp Digicon homes (SML pins at Stop)
- Mix C&O-1980 homes with AAR-1946 dwarfs
- Put `IH` in the MQTT topic leaf
- Store tables from a CATS session
