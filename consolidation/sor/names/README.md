# Names SoR (consolidation draft)

**Decision D2:** single authority = `public_name_map.csv` (Device Map grammar).

| File | Role |
|------|------|
| `public_name_map.csv` | Snapshot of live apply map |
| `public_name_map_merged.csv` | Draft with block_display `notes` merged (D2b) |
| `block_display_names.csv` | Legacy index snapshot — retire when D2 batch lands |

## Validation (read-only)

```bash
python3 consolidation/scripts/propose_os_from_map.py
python3 consolidation/scripts/check_hart_phase02_from_map.py
python3 consolidation/validators/check_names_diff.py
```

`check_phase02_from_map.sh` wrapper: **PASS** (2026-08-31).

## Consumers

See [`audits/names-consumers.md`](../../audits/names-consumers.md).

## Refresh live snapshot

```bash
cp jmri/layouts/hart/data/public_name_map.csv consolidation/sor/names/
cp jmri/layouts/hart/data/block_display_names.csv consolidation/sor/names/
python3 consolidation/scripts/merge_block_display_notes_into_map.py
```

Live map is read-only during consolidation build.
