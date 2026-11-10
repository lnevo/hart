# Publications

Rebuild scripts for official HART Railroad operating documents.

Outputs are written to `docs/ops/` in the hart repo. Edit the content dicts in these
scripts, then regenerate.

| Script | Publication |
|--------|-------------|
| `rebuild_scale_operating_instructions.py` | EQ-01 Scale Operating Instructions |
| `rebuild_dispatcher_train_list.py` | DS-01 Dispatcher Train List |
| `rebuild_yardmaster_sequence.py` | YM-01 Yardmaster Sequence |
| `rebuild_crew_instructions.py` | CI-D749 / CI-NVL / CI-CK1 (one sheet per job) |
| `rebuild_station_map.py` | SM-01 Station Map (subdivision schematic) |
| `rebuild_local_station_maps.py` | SM-02…05 West Yard / South Yard / East End / Shenango |
| `rebuild_operator_primer.py` | HB-01 New Operator Primer |
| `update_tt23_station_map.py` | Swap SM-01 schematic into TT-23 trifold left panel |
| `hart_pub_helpers.py` | Shared masthead / table helpers; diagram + narrow TT-23 page |

```bash
.venv/bin/python publications/rebuild_scale_operating_instructions.py
.venv/bin/python publications/rebuild_dispatcher_train_list.py
.venv/bin/python publications/rebuild_yardmaster_sequence.py
.venv/bin/python publications/rebuild_crew_instructions.py
.venv/bin/python publications/rebuild_station_map.py
.venv/bin/python publications/rebuild_local_station_maps.py
.venv/bin/python publications/rebuild_operator_primer.py
.venv/bin/python publications/update_tt23_station_map.py
```

**TT-23 station map archives** (under `publications/assets/`):

- `station_map_subdivision_tt23_original.png` — original linear left-panel diagram
- `TT-23_Route23_NevilleQueen_RevisionA_v6_pre_map_replace.pptx` — full trifold before the swap
