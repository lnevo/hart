# hart-ops

HART operations tooling: car inventory SoR, car cards, waybills, publications, and industry routing.

Part of the hart repo since 2026-11-09 (ADR-019); it was the separate `lnevo/hart-ops` repo before, now archived.

## Car inventory SoR (D11)

| File | Role |
|------|------|
| `data/image_metadata.csv` | **Editable** — marks, weights, OCR, photos |
| `data/HART_MergedCarRoster.xml` | Generated canonical full fleet |
| `data/OperationsCarRoster.xml` | Generated export → JMRI Operations Pro |

Add cars with `bin/cars` (`intake`, `add`, `status`, `cards`, `publish`, `compare`). Steps are in hart `wiki/pipelines/car-workflow.md`.

STS seed (via `external/sts-helpers`) imports a **freight subset** only — passenger/caboose excluded by design.

## Photo path (local, not in git)

Set where final car photos live (repo default):

```bash
# hart repo
export HART_CAR_IMAGES_FINAL="$(cd ../.. && pwd)/ops/car-cards/car-images/CarImagesFinal"

```

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Golden smoke (Tier C)

```bash
.venv/bin/python card_pipeline/generate_single_card.py
# Compare to tests/golden/NW32800.docx
```

Golden car: **NW32800**

## Print templates & waybills (git)

| Path | Role |
|------|------|
| `card_pipeline/assets/Poker Size Sticker Sheet Template.docx` | Apostrophe Games 9-up sticker master. Not in git: download it once (link in `operator_logos/SOURCES.md`) |
| `card_pipeline/output/HART_Equipment_Card_Template.docx` | Equipment card mail-merge template |
| `card_pipeline/output/HART_Spot_Waybills.docx` | Spot waybill deck |
| `docs/print/waybills/` | Session CC/WB label sheets |

Full fleet print (`HART_All_Car_Cards.docx`, ~345 MB) is kept in hart at ops/car-cards/print — see hart `consolidation/packages/car-cards/`.

```bash
python card_pipeline/generate_card_template.py
python card_pipeline/generate_waybill_cards.py
python card_pipeline/generate_all_cards.py   # optional; large output
```

## STS session scripts

Wrappers in `bin/` delegate to `sts-docker-helpers` (submodule `hart/external/sts-helpers`):

```bash
export HART_STS_HELPERS=../hart/external/sts-helpers   # if needed
./bin/apply_hart_seed.sh --generate --merge-fleet
```

## Layout

| Path | Pipeline |
|------|----------|
| `card_pipeline/` | 12 Car cards |
| `data/` | 13 Waybills + roster SoR |
| `publications/` | 15 Publications rebuild |
| `docs/print/` | Car-card and waybill print archive |

Published documents live in the hart repo at `docs/ops/`.
| `industries/` | 16 Industry routing matrix |
| `operator_logos/` | Logos for sheets and labels; where each came from is in `operator_logos/SOURCES.md` |

## Meta-repo

See `hart/wiki/REPOS.md`.
