# Publications

Rebuild scripts for official HART Railroad operating documents.

Outputs are written to `docs/ops/` in the hart repo. The crew jobs (CI-D749, CI-NVL, CI-CK1), YM-01, DS-01, EQ-01,
the destination colors and the TT-23 back page take their text from the crew master
`ops/hart-ops/data/crew.json` (ADR-039), through `crew_master.py`; the site's `www/data/crew.json` is built from the
same master. Edit the master, then regenerate the docx and the site copy. A `docx` object in the master holds what
only the printed sheet uses, or wording the sheet prints differently from the site. A job's `site_note` is a sentence only the
site prints, after the summary. The other scripts still hold
their content in their own dicts.

| Script | Publication |
|--------|-------------|
| `rebuild_scale_operating_instructions.py` | EQ-01 Scale Operating Instructions |
| `rebuild_dispatcher_train_list.py` | DS-01 Dispatcher Train List |
| `rebuild_yardmaster_sequence.py` | YM-01 Yardmaster Sequence |
| `rebuild_crew_instructions.py` | CI-D749 / CI-NVL / CI-CK1 (one sheet per job) |
| `rebuild_station_map.py` | SM-01 Station Map (subdivision schematic) |
| `rebuild_local_station_maps.py` | SM-02…05 West Yard / South Yard / East End / Shenango (drawers in `local_station_maps/`, one module per station) |
| `rebuild_operator_primer.py` | HB-01 New Operator Primer |
| `update_tt23_station_map.py` | Swap SM-01 schematic into TT-23 trifold left panel |
| `hart_pub_helpers.py` | Shared masthead / table helpers; diagram + narrow TT-23 page |
| `crew_master.py` | Reads the crew master and builds the site and docx views of it (standard library only) |
| `crew_schema.py` | Schema check of the crew master: keys, required fields, references, `docx` fields |
| `build_crew_json.py` | Writes `www/data/crew.json` from the crew master; `--check` (the `crew-json` step of `check.sh`) |

```bash
.venv/bin/python publications/rebuild_scale_operating_instructions.py
.venv/bin/python publications/rebuild_dispatcher_train_list.py
.venv/bin/python publications/rebuild_yardmaster_sequence.py
.venv/bin/python publications/rebuild_crew_instructions.py
.venv/bin/python publications/rebuild_station_map.py
.venv/bin/python publications/rebuild_local_station_maps.py
.venv/bin/python publications/rebuild_operator_primer.py
.venv/bin/python publications/update_tt23_station_map.py
python3 publications/build_crew_json.py
```

**TT-23 station map archives** (under `publications/assets/`):

- `station_map_subdivision_tt23_original.png` — original linear left-panel diagram
- `TT-23_Route23_NevilleQueen_RevisionA_v6_pre_map_replace.pptx` — full trifold before the swap
