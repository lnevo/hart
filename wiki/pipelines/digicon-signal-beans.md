# Pipeline 3 — Digicon signal beans

JMRI Virtual heads + SignalHeadSignalMasts live in `tables.xml`; the wiring catalog (CSVs below) is generated from the head plan and must agree with them. Appearances are stock **Basic** (`two-searchlight` / `one-low`). No aspects are disabled (ADR-011). Layout Editor icons are `discriminated` at scale 1.0.

**Status:** Live.

## Inputs

- the head rows of [`jmri/layouts/hart/data/wiring.csv`](../../jmri/layouts/hart/data/wiring.csv) (one per disc; `hartlib.wiring.digicon_rows` gives the 3 pins)
- [`jmri/layouts/hart/output/signal_head_plan.csv`](../../jmri/layouts/hart/output/signal_head_plan.csv)

Packed MQTT leaf = radio node × 100 + UID (example: node 4, UID 0 → `432` / `IH432`).

## Outputs

- IH / SHSM beans in tables (Basic `two-searchlight` two-head; `one-low` dwarfs and dispatcher virtuals).

## Run

```bash
python3 jmri/layouts/hart/scripts/build_hart_signal_heads.py --wiring-only
```

Head IH numbers in `tables.xml` follow the wiring plan (packed = radio address × 100 + slot); `tools/audit/check_wiring_crosswalk.py` fails in `./tools/check.sh` when a head on a physical mast differs from `wiring.csv`. The script has one mode: it writes the head and mast plan CSVs from `wiring.csv`'s wired heads (`--wiring-only` is still accepted). A head is wired by its row in `jmri/layouts/hart/data/wiring.csv`; `tables.xml` is generated from the device master (ADR-029). An interim build with fewer heads than planned (Mast 6LB) has only its wired heads' rows in `wiring.csv`, and the head plan follows them.

Facing / SML chaining: [`docs/ctc/SIGNAL_FACING.md`](../../docs/ctc/SIGNAL_FACING.md). Decision: [`ADR-006-co-1980-signals.md`](../decisions/ADR-006-co-1980-signals.md).

MQTT SET uses packed topics `track/signalhead/<digits>` and field status `track/signalmast/<digits>` — not an include list. Live roster is LCOS mast traffic.

## Do not

- Use stock `SL-2-high-abs` for two-lamp Digicon homes (SML pins at Stop)
- Mix C&O-1980 homes with AAR-1946 dwarfs
- Put `IH` in the MQTT topic leaf
- Store tables from a CATS session
