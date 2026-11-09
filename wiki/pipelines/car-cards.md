# Pipeline 12 — Car cards

Print filled car cards from roster XML + cropped car photos.

**Status:** Live in the hart-ops submodule (`external/hart-ops/`). New cars go through `bin/cars` ([`car-workflow.md`](car-workflow.md)).

## Inputs

- `data/HART_MergedCarRoster.xml`, `data/OperationsEngineRoster.xml`
- `data/image_metadata.csv`
- Photos: `CarImagesFinal/` (and crop/OCR helpers in `card_pipeline/`)

## Outputs

- `card_pipeline/output/HART_All_Car_Cards.docx` (sticker sheet, 9 per page)

## Run

From `external/hart-ops/` (set up its `.venv` as in its README):

```bash
.venv/bin/python card_pipeline/generate_all_cards.py
```

Related: `generate_single_card.py`, `generate_card_template.py`, `build_merged_car_roster.py`, image OCR/crop scripts in `card_pipeline/`. Agent notes: `external/hart-ops/AGENTS.md`.
