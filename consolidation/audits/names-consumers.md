# Audit — names CSV consumers

**Date:** 2026-08-31

## Scope split (proposed D2)

| CSV | Role |
|-----|------|
| `public_name_map.csv` | Apply map: identity, proposed renames, device comments (ADR-005) |
| `block_display_names.csv` | Live CP/OS/track index (ADR-002); not the apply script |

## Consumers (live — read-only)

| Script | Reads | Writes |
|--------|-------|--------|
| `sync_public_name_map.py` | Device map | `public_name_map.csv` |
| `apply_public_names.py` | `public_name_map.csv` | `tables/new_tables.xml` |
| `apply_public_names_tree.py` | same | same (tree order) |
| `refresh_bean_comments.py` | map + wiring CSVs | tables XML |
| `audit_panel_contracts.py` | map + XML | — |
| `gen_ctc_track_plan.py` | `public_name_map.csv` | CTC artifacts |
| `cats/scripts/lcos_mqtt_mimic.py` | `public_name_map.csv` | — |
| `docs/wiring/scripts/refresh_wiring_docs.py` | `public_name_map.csv` | wiring xlsx |
| `bootstrap_hart_from_linear6.py` | `block_display_names.csv` | optional apply |

## Generator order (proposed)

```
sync_public_name_map → apply_public_names → refresh_bean_comments → (export pipelines)
```

## Consolidation artifacts

- Snapshots: `sor/names/public_name_map.csv`, `sor/names/block_display_names.csv`
- Validator: `validators/check_names_diff.py`
- Draft guide: `wiki/pipelines/public-names.md`
