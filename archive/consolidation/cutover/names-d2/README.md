# Cutover — names D2 single SoR

**Status:** Draft SoR in consolidation; live map **unchanged**

## Standalone consolidation copies

| Artifact | Path |
|----------|------|
| Merged map (D2b) | `sor/names/public_name_map_merged.csv` |
| Live snapshot | `sor/names/public_name_map.csv` |
| Legacy snapshot | `sor/names/block_display_names.csv` |

## Validators (read-only, PASS)

- `check_phase02_from_map.sh`
- `check_names_diff.py`
- `propose_os_from_map.py`

## Cutover batch (future — all consumers together, D2d)

1. Replace live `public_name_map.csv` with merged draft (after human review)
2. Retire `block_display_names.csv` (D2a)
3. Promote `check_hart_phase02_from_map.py` to live phase02
4. Update `refresh_bean_comments`, bootstrap, ADR-002

**Live files not touched during consolidation build.**

## Test before cutover

- Tier A green including map-derived phase02
- Manual review of merged `notes` column vs block_display
