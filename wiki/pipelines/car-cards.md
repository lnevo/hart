# Pipeline 12 — Car cards

Print filled car cards from roster XML + cropped car photos.

**Status:** Live on Desktop (not the hart git tree). `~/Desktop/HART/Car Cards/`

## Inputs

- `data/HART_MergedCarRoster.xml`, `data/OperationsEngineRoster.xml`
- `data/image_metadata.csv`
- Photos: `CarImagesFinal/` (and crop/OCR helpers in `card_pipeline/`)

## Outputs

- `card_pipeline/output/HART_All_Car_Cards.docx` (sticker sheet, 9 per page)

## Run

From `~/Desktop/HART/Car Cards/`:

```bash
.venv/bin/python card_pipeline/generate_all_cards.py
```

Related: `generate_single_card.py`, `generate_card_template.py`, `build_merged_car_roster.py`, image OCR/crop scripts in `card_pipeline/`. Agent notes: `Car Cards/AGENTS.md`.
