# Pipeline 15 — Ops publications

Rebuild official HART crew/dispatcher paperwork from Python content dicts.

**Status:** Live. Sources are in `external/hart-ops/publications/`; outputs go to `docs/ops/`.

## Inputs

- Content in each `rebuild_*.py`
- Assets under `external/hart-ops/publications/assets/` (station map PNG, TT-23 trifold)

## Outputs (in `docs/ops/`)

| Pub | File |
|-----|------|
| EQ-01 | `HART Railroad Scale Operating Instructions.docx` |
| DS-01 | `Neville_Island_Dispatcher_Train_List.docx` |
| YM-01 | `Neville_Island_Yardmaster_Sequence.docx` |
| CI-* | `Neville_Island_Crew_{D749,NVL,CK1}.docx` |
| SM-01 | `Neville_Island_Station_Map.docx` |
| SM-02…05 | West Yard / South Yard / East End / Shenango maps |
| HB-01 | `Neville_Island_New_Operator_Primer.docx` |
| TT-23 | `TT-23_Route23_NevilleQueen_RevisionA_v6.pptx` (map swap script) |

## Run

```bash
make publications
```

This runs `tools/ops/rebuild_publications.sh`, which creates the `external/hart-ops/.venv` if needed and runs each `rebuild_*.py` plus `update_tt23_station_map.py`.

Standards: `docs/ops/HART_Railroad_Publication_Standards_v1.0.docx`. Index: `docs/ops/README.md`.
