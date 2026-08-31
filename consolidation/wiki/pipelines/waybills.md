> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record (consolidation view)

| Kind | Live path (read-only) | Proposed consolidation path |
|------|----------------------|----------------------------|
| Runbook | `wiki/pipelines/waybills.md` | `consolidation/wiki/pipelines/waybills.md` |
| Artifacts | See live guide below | `consolidation/sor/` when promoted |

---

# Pipeline 13 — Waybills

Generate spot waybill cards and CC/waybill labels from the HART waybill matrix.

**Status:** Live on Desktop. Same tree as car cards. CSV also seeds STS (pipeline 14).

## Inputs

- `data/HART_Spot_Waybills.csv`
- `data/spot_assignments.csv`
- `operator_logos/` for labels

## Outputs

- `card_pipeline/output/HART_Spot_Waybills.docx`
- CC/waybill label docs from `generate_cc_waybill_labels.py`

## Run

From `~/Desktop/HART/Car Cards/`:

```bash
.venv/bin/python card_pipeline/generate_waybill_cards.py
.venv/bin/python card_pipeline/generate_cc_waybill_labels.py
```

Commodity / supplier / customer / via rules in `generate_waybill_cards.py` are the paper SoR; keep the CSV in sync with STS seed inputs under `sts-docker-helpers/seed/inputs/`.
