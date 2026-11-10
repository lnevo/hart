# Car cards pipeline

Raw photos → crop → OCR → car records → printed cards. The day-to-day tool is `ops/hart-ops/bin/cars` (ADR-013); the runbook is [`wiki/pipelines/intake-stages.md`](../../../wiki/pipelines/intake-stages.md). **Legacy raw `Images/` (~1 GB) are not mirrored.**

## Workspace layout

After `bash tools/ops/setup_car_cards_workspace.sh`:

```text
ops/car-cards/
  incoming/          ← drop new light-box photos here (JPEG/PNG)
  Images/            → symlink to incoming/ (pipeline expects this name)
  CarImages/         generated card crops
  CarImagesFinal/    → symlink to ../car-images/CarImagesFinal
  OcrZoom/           OCR debug bands
  data/              → symlink to ../../hart-ops/data
ops/hart-ops/card_pipeline/   scripts (SoR)
```

## Pipeline steps

```bash
ops/hart-ops/bin/cars status          # what is queued
ops/hart-ops/bin/cars intake          # crop, OCR and match new photos in incoming/
ops/hart-ops/bin/cars cards           # print cards for queued cars and locos
```

`bin/cars --help` lists every step (review, approve, fill, publish, compare and the rest).

## Environment

`tools/env/load_env.sh` sets `HART_CAR_CARDS_ROOT` (`ops/car-cards`) and `HART_CAR_IMAGES_FINAL` (`ops/car-cards/car-images/CarImagesFinal`); override them in `tools/env/hart.env`. [`tools/ops/setup_car_cards_workspace.sh`](../../../tools/ops/setup_car_cards_workspace.sh) creates the folders and links above.

## STS seed

Car photos for STS use `CarImagesFinal/` via `HART_CAR_IMAGES_FINAL` in hart-ops seed scripts.

## Print artifacts (templates + generated)

| Location | Contents |
|----------|----------|
| `ops/hart-ops/card_pipeline/assets/` | **Poker Size Sticker Sheet Template.docx** (git) |
| `ops/hart-ops/card_pipeline/output/` | Equipment template, spot waybills (git) |
| `ops/hart-ops/docs/print/waybills/` | Session CC/WB label decks (git) |
| `ops/car-cards/print/` | Full `HART_All_Car_Cards.docx` mirror (~345 MB, not git) |

Regenerate the blank equipment-card template and the spot waybill deck:

```bash
make waybills                          # runs run_generate_print.sh
GENERATE_ALL_CARDS=1 make waybills     # also the full fleet deck (large)
```

**Waybill / session scripts:** see [`WAYBILL_SCRIPTS.md`](WAYBILL_SCRIPTS.md) — spot waybills, STS `--refresh`, session rebuild, not-yet-printed workflow.
