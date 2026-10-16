> **Consolidation draft** — live sources are read-only. See [`LIVE_SOURCES.md`](../../LIVE_SOURCES.md).

## Source of record

| Kind | Live (read-only bench) | Build target |
|------|------------------------|--------------|
| Runbook | `wiki/pipelines/waybills.md` | this file |
| Matrix SoR | `consolidation/external/hart-ops/data/HART_Spot_Waybills.csv` | hart-ops |
| Legacy bench | `~/Desktop/HART/Car Cards/data/` | read-only (D12) |

**Tier:** C · **Repo:** `consolidation/external/hart-ops`

---

# Pipeline 13 — Waybills

Generate spot waybill cards and CC/waybill labels from the HART waybill matrix.

**Status:** **hart-ops** (`consolidation/external/hart-ops`). STS seed reads same CSV via `consolidation/external/sts-helpers`.

## Inputs

- `data/HART_Spot_Waybills.csv`
- `data/spot_assignments.csv`
- `operator_logos/`

## Run

```bash
cd consolidation/external/hart-ops
.venv/bin/python card_pipeline/generate_waybill_cards.py
.venv/bin/python card_pipeline/generate_cc_waybill_labels.py
```

Keep CSV in sync with `consolidation/external/sts-helpers/seed/inputs/` when waybill lanes change (hart-ops + helpers repos only — not Desktop).
