# ADR — Single names SoR (consolidation, D2 approved)

**Status:** Approved 2026-08-31  
**Supersedes (on promotion):** dual-CSV language in draft `ADR-consolidation-sor.md`

## Decision

**`public_name_map.csv` is the single source of truth** for equipment identity, proposed renames, device comments, and HART Device Map display.

`block_display_names.csv` is **legacy** — retain only until consumers are migrated or proven redundant.

## Rationale

- Device Map canvas syncs via `sync_public_name_map.py` into the map CSV.
- 676 map rows vs 53 block_display rows; 30 block_display-only values are mostly CP/plate/throat **metadata**, not separate equipment identity.
- Owner confirmed map is authority.

## Migration (promotion only — not live yet)

| Consumer | Today | Target |
|----------|-------|--------|
| `check_hart_phase02.py` | OS names from `block_display_names.csv` | Filter `public_name_map.csv` by role/layer or CP column |
| `bootstrap_hart_from_linear6.py` | Optional block_display apply | Remove or map-only |
| `refresh_bean_comments.py` | Text-replace path list includes block_display file | Drop from replace list after migration |
| `sor/names/` snapshot | Both CSVs | Map only after migration |

## Generator order (unchanged)

```
sync_public_name_map → apply_public_names → refresh_bean_comments → export pipelines
```

## Audit

[`audits/block-display-vs-map.md`](../audits/block-display-vs-map.md)
