# One-shot: OpenLCB routes IO:AUTO:0001–0004 (Switch 37/39)

**Date removed from live:** 2026-08-30 (one-shot; not immortal pipeline logic)  
**Pipeline:** 3 / Digicon tables

## What was removed

Routes for Switch 37/39 Closed/Thrown auto-staging — workaround no longer needed.

## Policy

Do **not** re-add to `cleanup_uss_ctc_leftovers.py` or any active cleanup script.

Reference: live `wiki/STATUS.md` note; removed from `tables/new_tables.xml` on branch.

## If similar one-shot needed again

1. Edit `tables/new_tables.xml` directly or via one documented script run.
2. Document in STATUS only.
3. Optionally copy delete list here for history — **do not** wire into forever-delete frozensets.
