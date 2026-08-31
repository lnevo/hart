# Audits index

Validator and review reports for the consolidation workspace.

## Latest validator run

See `run_all_*.log` and symlink `latest.log` in this folder.

```bash
bash consolidation/validators/run_all.sh
```

## Review reports

| Report | Topic |
|--------|-------|
| [script-headers.md](script-headers.md) | Live script/doc header audit |
| [tables-pipeline.md](tables-pipeline.md) | Tables chain + cleanup script review |
| [names-consumers.md](names-consumers.md) | CSV consumer map |
| [block-display-vs-map.md](block-display-vs-map.md) | D2 single SoR migration audit |
| [mqtt-static-refs.md](mqtt-static-refs.md) | D6 live roster / no static lists |

## Last run summary (2026-08-31)

| Check | Result |
|-------|--------|
| audit_strict | PASS |
| phase02 | PASS |
| names_diff | PASS |
| sml_invariants | PASS (93 destinations) |
| mqtt_static | PASS |
| wiring_crosswalk | PASS (72% overlap; 10 ID gap documented) |

**D2 note:** `propose_os_from_map.py` confirms map-derived OS covers all 23 legacy block_display OS rows.
