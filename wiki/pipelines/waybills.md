# Pipeline 13 — Waybills

Generate spot waybill cards and CC/waybill labels from the HART waybill matrix.

**Status:** Live in `ops/hart-ops/`, same tree as car cards. CSV also seeds STS (pipeline 14).

## Inputs

- `data/HART_Spot_Waybills.csv`
- `data/spot_assignments.csv`
- `data/industries.csv`: the industry master; both CSVs name an industry by its `industry_id` (ADR-039)
- `operator_logos/` for labels

## Outputs

- `card_pipeline/output/HART_Spot_Waybills.docx`
- CC/waybill label docs from `generate_cc_waybill_labels.py`

## Run

From `ops/hart-ops/`:

```bash
.venv/bin/python card_pipeline/generate_waybill_cards.py
.venv/bin/python card_pipeline/generate_cc_waybill_labels.py
```

Do not run `generate_waybill_cards.py` against the master until the owner decides: it rewrites `data/HART_Spot_Waybills.csv` and renumbers `card_id` from 1 (owner, 2026-11-25; live waybills and the print queue are in STS).

The rules are in `data/waybill_loads.csv`, `data/waybill_parties.csv` and `data/waybill_empty_returns.csv`, and the interchange cards are the interchange rows of `data/HART_Spot_Waybills.csv`; `card_pipeline/waybill_data.py` reads them through `hartlib.waybills` and `card_pipeline/waybill_deck.py` applies them. Keep the CSV in sync with STS seed inputs under `sts-docker-helpers/seed/inputs/`.
