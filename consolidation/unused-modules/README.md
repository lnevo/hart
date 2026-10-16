# unused-modules — retired pipeline logic

**Policy (D5 approved):** One-shot table deletes and obsolete cleanup paths must **not** live in active pipeline scripts forever.

## Purpose

Archive **retired** or **one-shot** logic here for reference — not executed in normal pipelines.

| Pattern | Example | Active home |
|---------|---------|-------------|
| One-shot OpenLCB route delete | IO:AUTO:0001–0004 (Switch 37/39) | STATUS note only; already removed from live |
| OpenLCB leftover MS01 sensors | [`tables/openlcb-leftover-sensors.md`](tables/openlcb-leftover-sensors.md) | Live `cleanup_uss_ctc_leftovers.py` (2-name minimal set) |
| Obsolete HEAD_NAMES patch | `build_hart_signal_heads.py` guard | Live code rejects HEAD_NAMES reintroduction |
| USS rename + orphan delete | `cleanup_uss_ctc_leftovers.py` | Live script (minimal deletes only) |

## Rules

1. New entries require: date, pipeline #, why retired, what replaced it.
2. **Never** run scripts from this folder against live XML without explicit promotion review.
3. Promotion = copy pattern into live script only if it is **ongoing** policy, not a one-shot.

## Layout (as needed)

```
unused-modules/
  README.md
  tables/          # retired table cleanup one-shots
  mqtt/            # retired static head lists
```

## Review gate

Before any live promotion from here: Tier A validators green + entry in `audits/tables-pipeline.md`.
