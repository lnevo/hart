# hart-ops — migration plan (P3a approved)

**Status:** Phase 1 **complete** (2026-08-31) · repo [`lnevo/hart-ops`](https://github.com/lnevo/hart-ops)  
**Submodule:** `hart/external/hart-ops` @ `bc6ce55`

## SoR build chain (D11)

```
image_metadata.csv  →  build_car_roster_sor.py  →  HART_MergedCarRoster.xml
                                                      ↓
                                    export_operations_roster.py  →  OperationsCarRoster.xml
```

JMRI Operations Pro receives **all cars**. STS seed reads Merged with freight-only filter.

---

## Repo layout (proposed)

```
hart-ops/
  README.md
  card_pipeline/          ← from Desktop/Car Cards/card_pipeline/
  data/
    OperationsCarRoster.xml   # GENERATED → JMRI Operations Pro (all cars)
    HART_MergedCarRoster.xml  # GENERATED canonical full fleet
    image_metadata.csv        # EDITABLE SoR (marks, weights, OCR, photos)
    HART_Spot_Waybills.csv
    …
  publications/           ← rebuild scripts + templates
  industries/             ← from Desktop/HART/Industries/
  sts-helpers/            ← Car Cards/sts-docker-helpers/ (or submodule later)
  tests/
    golden/
      NW32800.docx        ← committed golden output (small)
    test_golden_card.py
  docs/
    GOLDEN_SMOKE.md
    PHOTO_SOR.md          ← link audits/golden-car-sor.md content
  .gitattributes          ← LFS rules (see below)
  requirements.txt        ← from Car Cards/.venv export
```

---

## What moves from Desktop (phase 1)

| Source | Target | Notes |
|--------|--------|-------|
| `Car Cards/card_pipeline/` | `card_pipeline/` | Scripts + `assets/` (incl. `NW32800.png`, logos) |
| `Car Cards/data/*.xml`, `*.csv` | `data/` | Roster + metadata SoR |
| `Car Cards/publications/` | `publications/` | Pipeline 15 |
| `Car Cards/docs/` | `publications/output/` or `docs/published/` | Published docx/pptx SoR |
| `Industries/` | `industries/` | Pipeline 16 matrix |
| `Car Cards/sts-docker-helpers/` | `sts-helpers/` | Until P3b submodule split |

**Do not git-clone in phase 1:**

| Path | Reason |
|------|--------|
| `CarImagesFinal/` (~84 PNGs, large) | Local path or Git LFS bucket; document in README |
| `CarImagesCardFill/` | Regenerable intermediate |
| Raw phone originals (if separate folder) | Operator storage only |
| `Car Cards/.venv/` | Recreate from `requirements.txt` |

---

## LFS policy (draft)

| Pattern | Policy |
|---------|--------|
| `tests/golden/*.docx` | Plain git (small) |
| `card_pipeline/assets/*.png` | Plain git (logos + NW32800 only) |
| `CarImagesFinal/**` | **Not in repo** — env var `HART_CAR_IMAGES_FINAL` |
| Class-F archive media | Stay in `hart/docs/archive/` after P4a ingest |

---

## Migration checklist (phase 1 — done in hart-ops repo)

1. ~~Create **`lnevo/hart-ops`** on GitHub.~~ Done @ `bc6ce55`
2. ~~Copy phase-1 tree from Desktop~~ — one-time copy into **hart-ops**; **Desktop/HART unchanged**
3. Submodule: `hart/external/hart-ops`

## Not during consolidation (cutover project)

- Editing or slimming **`~/Desktop/HART/`**
- Pushing roster to **Pi** or layout hosts
- Overwriting live **`hart`** paths
- Replacing Desktop bench paths with symlinks

---

## Pipelines covered

| # | Name | hart-ops home |
|---|------|---------------|
| 12 | Car cards | `card_pipeline/` |
| 13 | Waybills | `data/HART_Spot_Waybills.csv` |
| 14 | STS helpers | `sts-helpers/` |
| 15 | Publications | `publications/` |
| 16 | Industries | `industries/` |

---

## Blocked until cutover project

- Touching **`~/Desktop/HART/`** (slim, dedupe, symlinks)
- Pi / host deploy of generated rosters
- Live promotion from consolidation
