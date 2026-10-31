# Audit — block_display_names vs public_name_map

**Date:** 2026-08-31  
**Decision:** D2 — single SoR = `public_name_map.csv`

## Counts

| File | Rows | Columns |
|------|------|---------|
| `public_name_map.csv` | 676 | layer, current, proposed, cp, hardware, comment, notes |
| `block_display_names.csv` | 53 | current_user_name, public_user_name, cp, role, notes |

## Overlap

- **30 values** appear only in `block_display_names` (not as map current/proposed).
- **186 map names** not present as values in block_display.

## block_display-only values (sample)

These are **metadata / CP labels / throat notes**, not full equipment rows in the map:

- CP areas: `Brick`, `Plane`, `Princess`, `South Yard`, `East End`, `Barn`
- Plate / throat: `hidden throat; same occupancy as Track S-R`, `Switch 23a`, `Switch 35b`
- Roles: `hand-throw`, `interchange`, `Crossover leg`
- Raw occupancy refs: `occupancy Block 13-5 / M2S1304`

## Live consumers of block_display

| Script | Usage |
|--------|-------|
| `jmri/scripts/check_hart_phase02.py` | OS `public_user_name` → layoutturnout blockname check |
| `jmri/scripts/bootstrap_hart_from_linear6.py` | Optional apply (hart bootstrap done) |
| `refresh_bean_comments.py` | Path in text-replace target list |

## Recommendation (consolidation → promotion)

1. Add **`role`** or use existing **`layer` + `cp` + `notes`** on map rows for OS/plate/throat metadata currently only in block_display.
2. Change `check_hart_phase02.py` to read OS expectations from map (filter `role=os` equivalent).
3. Remove `block_display_names.csv` from repo after one green validator cycle.
4. Until promotion: keep block_display as **read-only legacy**; do not edit live.

## Proposed map filter (draft)

For phase02 OS check, derive from map:

```python
# rows where layer indicates OS block public name on layoutturnout
# OR cp + notes encode plate/throat (migrate 53 rows into map notes/cp columns)
```

Detail in [`ADR-names-single-sor.md`](../wiki/decisions/ADR-names-single-sor.md).
