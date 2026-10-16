# Pipeline 15 — Ops publications

Rebuild official HART crew/dispatcher paperwork from Python content dicts.

**Status:** Live on Desktop. `~/Desktop/HART/Car Cards/publications/` → `docs/`.

## Inputs

- Content in each `rebuild_*.py`
- Assets under `publications/assets/` (station map PNG, TT-23 trifold)

## Outputs (in `Car Cards/docs/`)

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
cd ~/Desktop/HART/Car\ Cards
.venv/bin/python publications/rebuild_scale_operating_instructions.py
.venv/bin/python publications/rebuild_dispatcher_train_list.py
.venv/bin/python publications/rebuild_yardmaster_sequence.py
.venv/bin/python publications/rebuild_crew_instructions.py
.venv/bin/python publications/rebuild_station_map.py
.venv/bin/python publications/rebuild_local_station_maps.py
.venv/bin/python publications/rebuild_operator_primer.py
.venv/bin/python publications/update_tt23_station_map.py
```

Index: `Car Cards/docs/README.md`. Standards: `HART_Railroad_Publication_Standards_v1.0.docx`. Root Desktop Word files (orientation packet, old train lists) are drafts unless they match these pubs.
