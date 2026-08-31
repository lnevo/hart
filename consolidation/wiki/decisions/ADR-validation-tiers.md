# ADR — Validation tiers

**Status:** Accepted (consolidation) · 2026-08-31  
**Locks:** D1, D9 · [`DECISIONS_RECORDED.md`](../../DECISIONS_RECORDED.md)

## Tiers

| Tier | When | Pipelines | Command / doc |
|------|------|-----------|---------------|
| **A** | Before promotion to live; consolidation CI | 2, 3, 4, 8 | `bash consolidation/validators/run_all.sh` |
| **B** | Before deploy (`sync_hart_package.sh`) | 5, 6, 7, 9 | [`validators/TIER_B_MANUAL_SMOKES.md`](../../validators/TIER_B_MANUAL_SMOKES.md) |
| **C** | Ops session | 12–16 | Golden specs in `cross-repo/hart-ops/` |

## Tier A checks (`run_all.sh`)

| Check | Script | Notes |
|-------|--------|-------|
| Panel contracts | `check_audit_strict.sh` | drift=0 strict |
| Phase02 (live) | `check_phase02.sh` | block_display OS list |
| Phase02 (map draft) | `check_phase02_from_map.sh` | D2c prep |
| Names diff | `check_names_diff.py` | 17 virtual masts excluded (D2f) |
| SML | `check_sml_invariants.py` | 93 destinations |
| MQTT static lists | `check_mqtt_no_static_lists.py` | D6 |
| Wiring crosswalk | `check_wiring_crosswalk.py` | mast-aware via `sor/wiring/packed_id_crosswalk.csv` |

Reports: `consolidation/audits/run_all_*.log` · symlink `latest.log`

## Promotion gate

Tier A must pass before any consolidation artifact replaces a live path (explicit user request per file).
