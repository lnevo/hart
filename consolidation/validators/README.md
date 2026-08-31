# Validators — consolidation

Read-only checks against live layout. Reports under `consolidation/audits/`.

## Tier A (automated)

```bash
bash consolidation/validators/run_all.sh
```

| Script | Purpose |
|--------|---------|
| `check_audit_strict.sh` | Panel contract drift |
| `check_phase02.sh` | Phase 0–2 (live OS list) |
| `check_phase02_from_map.sh` | Phase 0–2 (map-derived OS, D2c draft) |
| `check_names_diff.py` | Map vs bean userNames |
| `check_sml_invariants.py` | 93 SML destinations |
| `check_mqtt_no_static_lists.py` | D6 live roster |
| `check_wiring_crosswalk.py` | Mast-aware wiring ↔ IH |

## Tier B (manual)

[`TIER_B_MANUAL_SMOKES.md`](TIER_B_MANUAL_SMOKES.md) — before `sync_hart_package.sh`

## Tier C (ops / deferred)

[`cross-repo/hart-ops/GOLDEN_SMOKE_CAR_CARDS.md`](../cross-repo/hart-ops/GOLDEN_SMOKE_CAR_CARDS.md)

## Supporting scripts (not in run_all)

| Script | Purpose |
|--------|---------|
| `../scripts/build_wiring_crosswalk.py` | Regenerate wiring crosswalk CSV |
| `../scripts/inventory_desktop_hart.py` | Desktop/HART root scan |
| `../scripts/propose_os_from_map.py` | D2 OS derivation check |
