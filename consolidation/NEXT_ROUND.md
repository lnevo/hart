# Next round — consolidation

**Updated:** 2026-08-31

---

## Scope

**Consolidation workspace only** — build docs, validators, audits, hart-ops, and submodule pins. Live layout, Desktop/HART, Pi, and STS runtime are **out of scope** for this effort.

---

## Completed

| Area | Output |
|------|--------|
| Meta-repo | `external/*` submodules + manifest pins |
| hart-ops | github.com/lnevo/hart-ops @ `c276b85` |
| Tranche A | manifest + pipeline guides 12–16 |
| Tranche B | `class_f_ingest_manifest.csv` (124 rows) |
| Tranche C | metadata-first roster + golden test |
| Decisions | D1–D12, ADRs, bench freeze |
| Validators | Tier A — ALL PASSED |

---

## Continue here (consolidation branch work)

| Item | Path |
|------|------|
| Tier A validators | `bash consolidation/validators/run_all.sh` |
| Class-F review rows (optional) | `sor/desktop/class_f_ingest_manifest.csv` |
| D2 draft validation | `sor/names/public_name_map_merged.csv` |
| Tier B smoke docs | `validators/TIER_B_MANUAL_SMOKES.md` |
| Portal rebuild | `python3 consolidation/scripts/build_site.py` |

---

## Commands

```bash
bash consolidation/validators/run_all.sh
python3 consolidation/scripts/build_site.py
cd external/hart-ops && python card_pipeline/build_car_roster_sor.py
```
