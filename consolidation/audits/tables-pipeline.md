# Audit — tables pipeline and cleanup scripts

**Date:** 2026-08-31

## Live chain (documented)

1. `sync_public_name_map.py` — device map → CSV
2. `apply_public_names.py` — CSV → bean userName
3. `refresh_bean_comments.py` — comments on beans
4. Pipeline exports (SML, heads, CTC) → `tables/new_tables.xml`
5. Sync → `jmri/layouts/hart/output/tables.xml`

See [`wiki/decisions/ADR-tables-merge-order.md`](../wiki/decisions/ADR-tables-merge-order.md).

## `cleanup_uss_ctc_leftovers.py` review

**Live file:** `jmri/layouts/hart/scripts/cleanup_uss_ctc_leftovers.py`

| Item | Finding |
|------|---------|
| OpenLCB routes IO:AUTO:0001–0004 | **Not present** in `DELETE_SYSTEM_NAMES` (one-shot removal already done) |
| Current deletes | Two `MS01.01.02…` OpenLCB leftover **sensors** only |
| MTT* protection | Assert + skip delete for `MTT*` LCC aliases |
| Writes | `--apply` touches `output/tables.xml`, `new_tables.xml`, `hart_prod.xml` |

## Recommendation (D5)

- **No urgent live refactor** — immortal list is already minimal.
- Refactored copy for documentation: `consolidation/scripts/cleanup_uss_ctc_leftovers.py` (optional; separates USS rename vs delete concerns for future promotion).

## Policy

Do not add one-shot table deletes to `DELETE_SYSTEM_NAMES` as permanent policy. Document one-shots in STATUS only.
