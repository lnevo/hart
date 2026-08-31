# hart-ops — migration target

**Status:** **Live** @ [`lnevo/hart-ops`](https://github.com/lnevo/hart-ops) · submodule `external/hart-ops`  
**Pin:** [`SUBMODULE_PIN.md`](SUBMODULE_PIN.md) · `bc6ce55`

## Scope (pipelines 12–16)

| Pipeline | Desktop path | Repo target |
|----------|--------------|-------------|
| 12 Car cards | `Car Cards/card_pipeline/` | `hart-ops/card_pipeline/` |
| 13 Waybills | `Car Cards/data/HART_Spot_Waybills.csv` | `hart-ops/data/` |
| 14 STS helpers | `Car Cards/sts-docker-helpers/` | `hart-ops/sts-helpers/` (submodule later) |
| 15 Publications | `Car Cards/publications/` | `hart-ops/publications/` |
| 16 Industries | `~/Desktop/HART/Industries/` | `hart-ops/industries/` |

## Out of scope for git (large binaries)

- `CarImagesFinal/` — local path or LFS bucket; env var `HART_CAR_IMAGES_FINAL`
- Desktop root class **F** media — ingest to `hart/docs/archive/` per [`audits/class-f-ingest-plan.md`](../../audits/class-f-ingest-plan.md)

## Golden smoke

- Spec: [`GOLDEN_SMOKE_CAR_CARDS.md`](GOLDEN_SMOKE_CAR_CARDS.md)
- Car: **NW32800**
- SoR audit: [`audits/golden-car-sor.md`](../../audits/golden-car-sor.md)

## Submodules (P3b)

hart-ops is sibling to `external/sts-helpers` in hart meta-repo. STS helpers stay submodule; car SoR moves into hart-ops when repo exists.
