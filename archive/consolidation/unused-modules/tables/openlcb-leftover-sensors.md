# OpenLCB leftover sensor delete (one-shot)

**Retired:** 2026-08 (USS CTC pack cleanup)  
**Pipeline:** #5 tables / USS CTC leftovers  
**Live script:** `jmri/layouts/hart/scripts/cleanup_uss_ctc_leftovers.py` (minimal delete set remains)

## What it did

Removed unreferenced OpenLCB sensor beans after the 20-column USS CTC pack:

```
MS01.01.02.00.00.FF.00.EA;01.01.02.00.00.FF.00.EB
MS01.01.02.00.00.FF.00.EC;01.01.02.00.00.FF.00.ED
```

These were **leftover route/sensor rows**, not MTT OpenLCB turnout aliases (those stay — device map DCC Switch N).

## Why archived here (D5)

One-shot deletes must not accumulate forever in active cleanup scripts. Live script keeps only the two names above with an assert that `MTT*` is never listed.

## Consolidation copy

Refactored reference: `consolidation/scripts/cleanup_uss_ctc_leftovers.py` — same delete set; documents USS vs Digicon split.

## Do not re-run

Beans are already gone from deploy `tables.xml`. Re-adding this delete list to a live script would be a no-op at best.

## Promotion rule

If a **new** one-shot delete is needed, add an entry here first; do not append to live `cleanup_uss_ctc_leftovers.py` without review.
