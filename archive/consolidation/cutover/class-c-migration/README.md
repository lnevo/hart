# Cutover — class C Desktop → hart-ops

**Status:** Standalone mirror **exists** in `consolidation/external/hart-ops/`  
**Desktop source:** `~/Desktop/HART/Car Cards/`, `Industries/` — **unchanged**

## What consolidation already holds

| Desktop subtree | Standalone copy | Pipeline |
|---------------|-----------------|----------|
| `Car Cards/card_pipeline/` | `hart-ops/card_pipeline/` | 12 |
| `Car Cards/data/` | `hart-ops/data/` | 12–13 |
| `Car Cards/publications/` | `hart-ops/publications/` | 15 |
| `Industries/` | `hart-ops/industries/` | 16 |

## Not copied (by design)

| Path | Reason |
|------|--------|
| `Car Cards/CarImagesFinal/` | ~GB photos — local/LFS path |
| Full Desktop tree | Inventory only — [`hart_subtree_inventory.csv`](../sor/desktop/hart_subtree_inventory.csv) |

## Cutover action (future)

Replace Desktop bench paths with README links to hart-ops git + env vars. **Do not delete Desktop until verified.**

## Test before cutover

- `python card_pipeline/build_car_roster_sor.py`
- `pytest tests/test_golden_card.py` (NW32800)
- Publications py_compile (see [`audits/hart-ops-publications.md`](../audits/hart-ops-publications.md))
