# hart-ops — consolidation external module

**Repo:** [`lnevo/hart-ops`](https://github.com/lnevo/hart-ops)  
**Path:** `consolidation/external/hart-ops`  
**Pin:** [`SUBMODULE_PIN.md`](SUBMODULE_PIN.md) · `761c1f9`

## Scope (pipelines 12–16)

| Pipeline | Content | Repo path |
|----------|---------|-----------|
| 12 Car cards | card pipeline, OCR, merge roster | `card_pipeline/` |
| 13 Waybills | spot assignments | `data/HART_Spot_Waybills.csv` |
| 14 STS | seed helpers (sibling submodule) | `consolidation/external/sts-helpers` |
| 15 Publications | rebuild scripts | `publications/rebuild_*.py` |
| 16 Industries | routing matrix | `industries/` |

## Car SoR (D11)

```
data/image_metadata.csv  →  HART_MergedCarRoster.xml  →  OperationsCarRoster.xml
```

Build: `python card_pipeline/build_car_roster_sor.py`  
Golden: **NW32800** — [`GOLDEN_SMOKE_CAR_CARDS.md`](GOLDEN_SMOKE_CAR_CARDS.md)

## Publications audit

[`audits/hart-ops-publications.md`](../../audits/hart-ops-publications.md) — 8 rebuild scripts verified present.

## Large binaries (not in git)

- Car final photos — local path / LFS; env `HART_CAR_IMAGES_FINAL`
- Desktop class **F** media — browse only via [`html/archive/f-root-index.html`](../../html/archive/f-root-index.html)

## Migration history

[`MIGRATION_PLAN.md`](MIGRATION_PLAN.md)
