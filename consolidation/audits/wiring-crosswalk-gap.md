# Audit — wiring crosswalk gap (packed ID vs live IH)

**Date:** 2026-08-31  
**Validator:** `consolidation/validators/check_wiring_crosswalk.py` (naive packed ↔ IH digit match)  
**Crosswalk draft:** `sor/wiring/packed_id_crosswalk.csv` via `scripts/build_wiring_crosswalk.py`

## Summary

The Tier A wiring validator reports **26/36 (72%) overlap** — not missing hardware. Ten packed IDs in `cats/data/signal_wiring.csv` do not match any live `IH*` bean, and ten live `IH*` beans are not listed under those packed values. **Five of the “matches” are false positives** (same number, different mast).

Root cause: **`signal_wiring.csv` still mixes packing schemes** from bench export (node×100+uid, helix C11 11xx) with post–ADR-005 live bean numbering (IH12xx East End clusters, IH1xx Princess balloon).

## The ten wiring-only packed IDs

| Packed | Mast (wiring CSV) | Live IH | Notes |
|--------|-------------------|---------|-------|
| 232 | Mast 24RA (top) | **1232** | C2 node 2 uid 32 → live Head 24RA Top |
| 238 | Mast 24RA (bottom) | **1233** | |
| 233 | Mast 24L (top) | **1234** | |
| 239 | Mast 24L (bottom) | **1235** | |
| 234 | Mast 24RB | **1236** | |
| 1132 | Mast 40LB (top) | **132** | Helix C11 export; live Head 36RB Top / 40LB cluster |
| 1135 | Mast 40LB (bottom) | **133** | |
| 1133 | Mast 2036 | **134** | |
| 1134 | Mast 2035 | **141** | |
| 1136 | Mast 40LA | **142** | |

## The ten bean-only IH IDs

| Live IH | Head userName | Mast | Wiring gap |
|---------|---------------|------|------------|
| 1237–1241 | Head 34L/32R/34R | Mast 34L, 32R, 34R | Wiring CSV lists **1232–1236** for these masts — numbers collide with Mast 24 cluster |
| 134, 141, 142 | Head 2036, 2035, 40LA | Princess | Covered by helix remap above |
| 137, 138 | Head 36RB Top/Bottom | Mast 36RB | Wiring uses packed **132/133** (direct match on IH digits for 36RB top/bottom rows) |

## False-positive “matches” (same number, wrong mast)

Wiring CSV rows with packed **1232–1236** name Mast 34L / 32R / 34R, but deploy `tables.xml` uses **IH1232–IH1236** for **Mast 24RA / 24L / 24RB**. The naive validator counts these as overlap; they are **not** the same signals.

Consolidation crosswalk marks these `status=collision`. Mast-aware validation should replace raw packed comparison.

## Consolidation action (no live edit)

1. Keep **`packed_id_crosswalk.csv`** under `sor/wiring/` as the remap table for validators and MQTT topic audits.
2. When **`docs/wiring/`** is next regenerated (explicit promotion), align packed column to live IH or drop stale node×100 rows.
3. Optional: extend validator to resolve via crosswalk + mast name (round 3 task #4).

## References

- Live map hardware column: `jmri/layouts/hart/data/public_name_map.csv` (mast → IH list)
- Princess facing notes: `cats/docs/SIGNAL_FACING.md` (IH1133/1134 historical vs live IH134/141)
- D4: git `docs/wiring/` is SoR — consolidation does not edit without promotion
