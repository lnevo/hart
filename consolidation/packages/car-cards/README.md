# Car cards pipeline (consolidation)

Raw photos → crop → OCR → metadata → printed cards. **Legacy raw `Images/` (~1 GB) are not mirrored**; the pipeline stays ready for new drops.

## Workspace layout

After `bash consolidation/scripts/setup_car_cards_workspace.sh`:

```text
external/desktop-data/car-cards/
  incoming/          ← drop new light-box photos here (JPEG/PNG)
  Images/            → symlink to incoming/ (pipeline expects this name)
  CarImages/         generated card crops
  CarImagesFinal/    → symlink to ../car-images/CarImagesFinal
  OcrZoom/           OCR debug bands
  data/              → symlink to ../../hart-ops/data
external/hart-ops/card_pipeline/   scripts (SoR)
```

## Pipeline steps

```bash
bash consolidation/packages/car-cards/run_process.sh

# Or manually:
cd consolidation/external/hart-ops
export HART_CAR_CARDS_ROOT="../desktop-data/car-cards"
export HART_CAR_IMAGES_FINAL="../desktop-data/car-images/CarImagesFinal"
.venv/bin/python card_pipeline/process_car_images.py
.venv/bin/python card_pipeline/finalize_car_images.py
.venv/bin/python card_pipeline/build_car_roster_sor.py
```

## Environment

```bash
export HART_CAR_IMAGES_FINAL="$(pwd)/../desktop-data/car-images/CarImagesFinal"
export HART_CAR_CARDS_ROOT="$(pwd)/../desktop-data/car-cards"
```

Set automatically by [`../../scripts/setup_car_cards_workspace.sh`](../../scripts/setup_car_cards_workspace.sh).

## STS seed

Car photos for STS use `CarImagesFinal/` via `HART_CAR_IMAGES_FINAL` in hart-ops seed scripts.

## Print artifacts (templates + generated)

| Location | Contents |
|----------|----------|
| `external/hart-ops/card_pipeline/assets/` | **Poker Size Sticker Sheet Template.docx** (git) |
| `external/hart-ops/card_pipeline/output/` | Equipment template, spot waybills, card review (git) |
| `external/hart-ops/docs/print/waybills/` | Session CC/WB label decks (git) |
| `external/desktop-data/car-cards/print/` | Full `HART_All_Car_Cards.docx` mirror (~345 MB, not git) |

Regenerate:

```bash
cd consolidation/external/hart-ops
.venv/bin/python card_pipeline/generate_card_template.py
.venv/bin/python card_pipeline/generate_waybill_cards.py
.venv/bin/python card_pipeline/generate_all_cards.py   # full fleet → output/ + mirror
```
