# Audit — hart-ops publications pipeline (15)

**Date:** 2026-08-31  
**Guide:** [`wiki/pipelines/ops-publications.md`](../wiki/pipelines/ops-publications.md)  
**Repo:** `consolidation/external/hart-ops` @ `761c1f9`

## Scripts present

| Script | Status |
|--------|--------|
| `publications/rebuild_scale_operating_instructions.py` | OK |
| `publications/rebuild_dispatcher_train_list.py` | OK |
| `publications/rebuild_yardmaster_sequence.py` | OK |
| `publications/rebuild_crew_instructions.py` | OK |
| `publications/rebuild_station_map.py` | OK |
| `publications/rebuild_local_station_maps.py` | OK |
| `publications/rebuild_operator_primer.py` | OK |
| `publications/update_tt23_station_map.py` | OK |
| `publications/hart_pub_helpers.py` | OK |
| `publications/assets/` | OK |

## Output target

`hart-ops/docs/published/` — index `docs/published/README.md`

## Class D root duplicates (Desktop)

These basenames match published hart-ops output; Desktop root copies are redundant:

- `HART Railroad Scale Operating Instructions.docx`
- `Neville_Island_Dispatcher_Train_List.docx`
- `Neville_Island_Yardmaster_Sequence.docx`
- `TT-23_Route23_NevilleQueen_RevisionA_v6.pptx`

## Consolidation build

Rebuild runs in **hart-ops only** — does not write Desktop or live `hart/docs/`.

```bash
cd consolidation/external/hart-ops
python3 publications/rebuild_scale_operating_instructions.py   # dry-run / verify imports
```

Full rebuild of all eight scripts is optional during consolidation; **py_compile: ALL OK** (2026-08-31).
