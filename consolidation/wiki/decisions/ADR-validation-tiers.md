# ADR — Validation tiers (consolidation draft)

**Status:** Draft — pending approval in [`DECISIONS_PENDING.md`](../../DECISIONS_PENDING.md) D1, D9.

## Tiers

| Tier | When | Pipelines | Command |
|------|------|-----------|---------|
| **A** | Before promotion to live; local consolidation CI | 2, 3, 4, 8 | `bash consolidation/validators/run_all.sh` |
| **B** | Before deploy (`sync_hart_package.sh`) | 5, 6, 7, 9 | Manual smokes in `manifest.yaml` |
| **C** | Ops session | 12–16 | Deferred |

## Tier A checks

1. `check_audit_strict.sh` — wraps `audit_panel_contracts.py --strict`
2. `check_phase02.sh` — wraps `check_hart_phase02.py`
3. `check_names_diff.py` — map vs bean userName
4. `check_sml_invariants.py` — 93 SML destinations
5. `check_wiring_crosswalk.py` — packed ID stub

Reports: `consolidation/audits/run_all_*.log`

## Promotion

Tier A must pass before any consolidation artifact replaces a live path.
