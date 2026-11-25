# Data masters: phase 1 lanes (2026-11-25)

Status: active

Plan for [ADR-039](../decisions/ADR-039-data-masters-in-git.md): one master per kind of record in git, column sidecars checked by `check.sh`, stable keys, and no spreadsheet as an input. Phase 2 (drift reports against STS, Operations Pro and JMRI, the SQLite view, and a database if one is ever needed) starts once phase 1 is done.

## Lanes

| Lane | Job | Owns | Starts after | Agent, review |
|---|---|---|---|---|
| L1 Catalogue | `docs/data/entities.csv` and its README: each kind of record, key, master, copies, outside tools, which side wins in a session. Proposes the master for locos, industries, trains, stations and control points; the owner confirms. | `docs/data/` | this page | `repo-auditor` drafts, main session writes; no review (docs) |
| L2 Validator | `tools/ops/check_data.py`, the extended sidecar format, the `data-schemas` step, sidecars for `devices` and `switches` converted | `tools/pipeline/checks.toml`, stamps, map node, `*.columns.csv` format | L1, and #1129 merged | `general-purpose`, opus; `/code-review medium` |
| L3 Wiring inputs | `build_wiring_json.py` and `create_wiring_schematic_ppt.py` read `hartlib.wiring`; v85 lamp pins and `signals_split_v8` exported once to frozen CSV | `www/scripts/build_wiring_json.py`, `tools/wiring/`, `docs/wiring/` | L1 | `general-purpose`, opus; `/code-review high` (`hartlib` reader) |
| L4a Industries | `industry_id` and spot keys across `spot_assignments.csv`, `HART_Spot_Waybills.csv`, `industries.json`; the routing matrix as CSV masters, xlsx written from them; sidecars | `ops/hart-ops/data/`, `ops/hart-ops/industries/`, `www/data/industries.json` and its readers | L2 | `general-purpose`, opus; `/code-review medium` |
| L4b Trains | train symbol as key in `hart_trains.csv` and `crew.json`; a writer recorded in the pipeline map; sidecar | `cats/data/hart_trains.csv`, `www/data/crew.json` readers | L2 | `general-purpose`; `/code-review medium` |
| L4c Places | one id for station and for control point across `stations.csv`, `interlockings.csv` and the devices' `cp`; block `id` in `occupancy_bindings.csv`; sidecars | `jmri/layouts/hart/data/schematic/`, `cats/data/occupancy_bindings.csv`, the CATS builders | L2, and no open schematic or naming PR on the same files | `schematic-builder`; `/code-review high` |
| L4d Locos | `roster_id` as key in `locos.csv`, `new_locos.json` built from it; sidecar | `ops/hart-ops/data/locos.csv`, `bin/cars locos` | L2 | `general-purpose`; `/code-review medium` |
| L5 Power districts | a master for power districts, from the owner's list; v86 and the layout docs read it | wherever L1 places it | L1 and the owner's list | main session |

L4c is the riskiest: it renames references that the panels and the CATS desks read. It runs last of the L4 lanes, with `make panels CHECK=1` and `make panelpro-test` before it merges.

## Rules for the lanes

- A lane edits only the files in its row. A file that two lanes need goes to the earlier lane, and the later one rebases.
- Only L2 edits `tools/pipeline/checks.toml`. Later lanes add sidecar files; the `data-schemas` step finds them.
- At most three lane agents at once, and fewer when the Mac's 8-session cap would be passed (count with `ListAgents` first).
- Lane agents leave this page, ADR-039 and `wiki/STATUS.md` alone and write their status lines to `.claude/progress/data-masters-<lane>.md`. The main session relays them and updates this table after each merge.
- Each lane opens its own PR from its own worktree, and runs `./tools/check.sh` (or `make remote`) before it pushes.

## Open for the owner

- The master for each kind L1 proposes (confirm in one batch of questions).
- The power district list.
- Whether the DecoderPro roster becomes a repo master or stays a copy on the Pi (phase 2).
