# Data masters: phase 1 lanes (2026-11-25)

Status: active

Plan for [ADR-039](../decisions/ADR-039-data-masters-in-git.md): one master per kind of record in git, column sidecars checked by `check.sh`, stable keys, and no spreadsheet as an input. Phase 2 (drift reports against STS, Operations Pro and JMRI, the SQLite view, and a database if one is ever needed) starts once phase 1 is done.

## Lanes

| Lane | Job | Owns | Starts after | Agent, review |
|---|---|---|---|---|
| L1 Catalogue | `docs/data/entities.csv` and its README: each kind of record, key, master, copies, outside tools, which side wins in a session. Masters chosen by the owner on 2026-11-25 (in `docs/data/README.md`). **Done** in the L1 PR. | `docs/data/` | this page | `repo-auditor` drafts, main session writes; no review (docs) |
| L2 Validator | `tools/ops/check_data.py`, the extended sidecar format, sidecars for `devices` and `switches` converted; the ADR-037 session adds the `data-schemas` step after its stage 4b | `tools/ops/check_data.py`, `*.columns.csv` format | L1 | `general-purpose`, opus; `/code-review medium` |
| L3 Wiring inputs | `build_wiring_json.py` and `create_wiring_schematic_ppt.py` read `hartlib.wiring`, not v86 (the signal split and v85 were archived on 2026-11-25) | `www/scripts/build_wiring_json.py`, `tools/wiring/`, `docs/wiring/` | L1 | `general-purpose`, opus; `/code-review high` (`hartlib` reader) |
| L4a Industries | new master `ops/hart-ops/data/industries.csv`; `industry_id` and spot keys across `spot_assignments.csv`, `HART_Spot_Waybills.csv`, `industries.json`; sidecars | `ops/hart-ops/data/`, `www/data/industries.json` and its readers | L2 | `general-purpose`, opus; `/code-review medium` |
| L4b Trains | new master `ops/hart-ops/data/trains.csv` keyed on train symbol; `cats/data/hart_trains.csv` built from it and recorded in the pipeline map; `crew.json` jobs checked against it; sidecar | `ops/hart-ops/data/trains.csv`, `cats/data/hart_trains.csv`, `www/data/crew.json` readers | L2 | `general-purpose`; `/code-review medium` |
| L4c Places | one id for station and for control point across `stations.csv`, `interlockings.csv` and the devices' `cp`; block `id` in `occupancy_bindings.csv`; sidecars | `jmri/layouts/hart/data/schematic/`, `cats/data/occupancy_bindings.csv`, the CATS builders | L2, and no open schematic or naming PR on the same files | `schematic-builder`; `/code-review high` |
| L4d Locos | `roster_id` as key in `locos.csv`, `new_locos.json` built from it; sidecar | `ops/hart-ops/data/locos.csv`, `bin/cars locos` | L2 | `general-purpose`; `/code-review medium` |

L4c is the riskiest: it renames references that the panels and the CATS desks read. It runs last of the L4 lanes, with `make panels CHECK=1` and `make panelpro-test` before it merges.

## Rules for the lanes

- A lane edits only the files in its row. A file that two lanes need goes to the earlier lane, and the later one rebases.
- No lane edits `tools/pipeline/checks.toml`, `tools/check.sh` or `check_stamps.py`: they belong to the ADR-037 session, which adds the `data-schemas` step. Later lanes add sidecar files; the step finds them.
- One merge at a time across sessions. The main session sends "ready #N" to the cleanup coordinator and merges only on "go #N": merge `origin/main` into the branch, push, wait for the required check on that head, merge, and repeat if `main` moved. No auto-merge.
- `wiki/STATUS.md` is frozen while the ADR-038 migration PR is open; after it lands, STATUS lines go in `wiki/status/` entry files.
- At most three lane agents at once, and fewer when the Mac's 8-session cap would be passed (count with `ListAgents` first).
- Lane agents leave this page, ADR-039 and `wiki/STATUS.md` alone and write their status lines to `.claude/progress/data-masters-<lane>.md`. The main session relays them and updates this table after each merge.
- Each lane opens its own PR from its own worktree. Full checks run only through `make remote`.

## Open for the owner

- Whether the DecoderPro roster becomes a repo master or stays a copy on the Pi (phase 2).
