> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record

| Kind | Live (read-only) | Consolidation draft |
|------|------------------|---------------------|
| Runbook | `wiki/pipelines/digicon-signal-beans.md` | this file |
| Wiring catalog | `cats/data/signal_wiring.csv` | crosswalk: `sor/wiring/packed_id_crosswalk.csv` |
| Head/mast plans | `cats/data/signal_head_plan.csv`, `signal_mast_plan.csv` | — |
| Appearances | `cats/resources/signals/hart-aar/` | — |

---

# Pipeline 3 — Digicon signal beans

Build JMRI Virtual heads + SignalHeadSignalMasts from the wiring catalog, plus the `hart-aar` two-head appearance set.

**Status:** Live.

## Inputs

- [`cats/data/signal_wiring.csv`](../../../cats/data/signal_wiring.csv) (3 pins per disc)
- [`cats/data/signal_head_plan.csv`](../../../cats/data/signal_head_plan.csv)
- [`cats/data/signal_mast_plan.csv`](../../../cats/data/signal_mast_plan.csv)

### Packed ID note

Wiring CSV **`packed`** column mixes schemes: node×100+uid (e.g. `432`), helix export (`1132`), and IH-shaped numbers that **collide** with live beans on different masts (e.g. wiring `1232` = Mast 34L, deploy `IH1232` = Mast 24RA). **Do not** validate wiring ↔ beans by raw packed digits alone.

Use consolidation crosswalk: [`audits/wiring-crosswalk-gap.md`](../../audits/wiring-crosswalk-gap.md) · regenerate with `scripts/build_wiring_crosswalk.py`.

Live MQTT topics use **deploy `IH*` digits** (`track/signalhead/<packed>` where packed matches bean systemName).

## Outputs

- IH / SHSM beans in tables (`hart-aar` `SL-2-digicon` two-head; AAR-1946 `SL-1-low` dwarfs)
- [`cats/resources/signals/hart-aar/`](../../../cats/resources/signals/hart-aar/)

## Run

```bash
python3 cats/scripts/build_hart_signal_heads.py
```

Facing / SML chaining: [`cats/docs/SIGNAL_FACING.md`](../../../cats/docs/SIGNAL_FACING.md).

MQTT SET uses packed topics `track/signalhead/<digits>` and field status `track/signalmast/<digits>`. Live roster = LCOS mast traffic (D6 — no static allow-lists).

## Validators

| Check | Script |
|-------|--------|
| Panel contracts | `validators/check_audit_strict.sh` |
| Wiring ↔ IH (mast-aware) | `validators/check_wiring_crosswalk.py` |
| MQTT static lists | `validators/check_mqtt_no_static_lists.py` |

## Do not

- Use stock `SL-2-high-abs` for two-lamp Digicon homes (SML pins at Stop)
- Put `IH` prefix in the MQTT topic leaf
- Store tables from a CATS session
