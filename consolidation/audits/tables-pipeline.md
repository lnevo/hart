# Audit — tables pipeline and cleanup scripts

**Date:** 2026-08-31 (updated)  
**Runbook:** [`wiki/pipelines/tables-merge.md`](../wiki/pipelines/tables-merge.md)  
**ADR:** [`wiki/decisions/ADR-tables-merge-order.md`](../wiki/decisions/ADR-tables-merge-order.md) (D3)

## Live chain (documented)

```
tables/new_tables.xml
    ↓ names, beans, SML, LE scripts
jmri/layouts/hart/output/tables.xml   (deploy bundle — LE + SML + CTC + Dispatcher)
    ↓ optional independent LE sync
jmri/layouts/hart/output/hart_prod.xml  (LE monitor only — not a substitute bundle)
```

### Stage scripts (live — read-only reference)

| Stage | Script | Writes |
|-------|--------|--------|
| Map sync | `sync_public_name_map.py` | CSV from device map |
| Names apply | `apply_public_names.py` | `new_tables.xml`, optionally bundle |
| Comments | `refresh_bean_comments.py` | `new_tables.xml`, bundle, `hart_prod.xml` |
| SML section sync | `sync_hart_sml_to_deployment.py` | **`signalmastlogics` only** in `output/tables.xml` |
| LE cleanup / yard / polish | `apply_le_cleanup.py`, `apply_yard_throat_blocks.py`, `polish_hart_layout_editor.py` | `new_tables.xml`; `--sync-output` → bundle + `hart_prod.xml` |
| CTC regen | `gen_ctc_track_plan.py` | `ctc/GUIObjects.xml`, targeted tables |
| CTC locking patch | `patch_ctc_locking.py` | `output/tables.xml` `<ctcdata>` in place |
| Dispatcher reconcile | `reconcile_dispatcher_stations.py` | `new_tables.xml`; optional bundle |
| Contract audit | `audit_panel_contracts.py --strict` | read-only gate |

**Forbidden:** whole-file `cp new_tables.xml → output/tables.xml`.

## `cleanup_uss_ctc_leftovers.py` review

**Live file:** `jmri/layouts/hart/scripts/cleanup_uss_ctc_leftovers.py`  
**Consolidation copy:** `consolidation/scripts/cleanup_uss_ctc_leftovers.py`

| Item | Finding |
|------|---------|
| OpenLCB routes IO:AUTO:0001–0004 | **Not present** in `DELETE_SYSTEM_NAMES` (one-shot removal already done) |
| Current deletes | Two `MS01.01.02…` OpenLCB leftover **sensors** only |
| MTT* protection | Assert + skip delete for `MTT*` LCC aliases |
| Writes | `--apply` touches `output/tables.xml`, `new_tables.xml`, `hart_prod.xml` |

Archived rationale: [`unused-modules/tables/openlcb-leftover-sensors.md`](../unused-modules/tables/openlcb-leftover-sensors.md)

## Recommendation (D5)

- **No urgent live refactor** — immortal delete list is already minimal.
- Consolidation copy documents USS vs Digicon split for future promotion review.
- New one-shots: archive under `unused-modules/tables/` first; do not append to live script without review.

## Policy

Do not add one-shot table deletes to `DELETE_SYSTEM_NAMES` as permanent policy. Document one-shots in STATUS or `unused-modules/` only.

## Tier A status

Run `bash consolidation/validators/run_all.sh` — tables-related checks include `audit_strict`, `sml_invariants`, and `phase02`.
