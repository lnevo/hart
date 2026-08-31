> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record

| Kind | Live (read-only bench) | Build target |
|------|------------------------|--------------|
| Runbook | `wiki/pipelines/car-cards.md` | this file |
| **hart-ops repo** | [`consolidation/external/hart-ops`](../../external/hart-ops) @ consolidation/external/ | **canonical ops workspace** |
| **Car inventory SoR** | `data/image_metadata.csv` → `HART_MergedCarRoster.xml` | [`sor/cars/README.md`](../../sor/cars/README.md) |
| JMRI export | `OperationsCarRoster.xml` (generated in hart-ops) | cutover project |
| Photos (local) | `HART_CAR_IMAGES_FINAL` env → Desktop `CarImagesFinal/` | not in git |

**Tier:** C · **ADR:** [`wiki/decisions/ADR-car-roster-single-sor.md`](../decisions/ADR-car-roster-single-sor.md) · **D12:** do not overwrite Desktop bench

---

# Pipeline 12 — Car cards

Print filled car cards from roster XML + cropped car photos.

**Status:** **hart-ops** repo (`consolidation/external/hart-ops`). Desktop `Car Cards/` is read-only bench until cutover.

## SoR (single inventory)

```
image_metadata.csv  →  build_car_roster_sor.py  →  HART_MergedCarRoster.xml  →  OperationsCarRoster.xml
```

STS and card pipeline are **filtered consumers** — see ADR.

## Run (hart-ops)

```bash
cd consolidation/external/hart-ops   
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export HART_CAR_IMAGES_FINAL=~/Desktop/HART/Car\ Cards/CarImagesFinal

python card_pipeline/build_car_roster_sor.py
.venv/bin/python card_pipeline/generate_all_cards.py
```

Golden smoke: **NW32800** — `tests/test_golden_card.py` · [`cross-repo/hart-ops/GOLDEN_SMOKE_CAR_CARDS.md`](../../cross-repo/hart-ops/GOLDEN_SMOKE_CAR_CARDS.md)
