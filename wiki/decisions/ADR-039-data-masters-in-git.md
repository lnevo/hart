# ADR-039 — One master per kind of record, kept in git

- **Status:** Accepted
- **Date:** 2026-11-25
- **Deciders:** lnevo
- **Plan:** [data masters project](../projects/data-masters.md) (lanes, order, who works on what)

## Context

The repo tracks about 810 CSV, JSON and XML files. About 270 are frozen under `archive/`, and most of the 390 JMRI XML files under `jmri/layouts/hart` are build outputs. The live STS keeps a session's state in MariaDB on the Pi (ADR-020), backed up nightly (ADR-035). So the repo already has a database. What it lacks is a rule for the rest of the data.

Some of the work is done. `docs/pipeline-map/pipeline_map.json` records who writes and reads each file. `hartlib.devices` is the one view of the devices, `switches.csv` holds the switch facts (ADR-021), `image_metadata.csv` is the car master (ADR-013), and generated views are not committed (ADR-036). `devices.columns.csv` and `switches.columns.csv` describe their columns.

The gaps are about kinds of record, not files. A review on 2026-11-25 found:

- **Locos** are in `ops/hart-ops/data/locos.csv`, `jmri/layouts/hart/data/new_locos.json`, `OperationsEngineRoster.xml`, STS and the DecoderPro roster on the Pi. The roster is not in the repo; only the Pi backups hold it.
- **Industries and spots** are keyed by name. `spot_assignments.csv`, `HART_Spot_Waybills.csv` and `www/data/industries.json` each spell the industry out, and STS and Operations Pro keep their own lists. The traffic flows, interchanges and suppliers are in a hand-kept spreadsheet, `ops/hart-ops/industries/HART_Industry_Routing_Matrix.xlsx`.
- **Blocks** are referred to by public name in `cats/data/occupancy_bindings.csv`, though public names change (ADR-005) and `block_lengths.csv` has a block `id`.
- **Trains** (`cats/data/hart_trains.csv`) have no writer in the pipeline map, and no key is defined for them.
- **Wiring.** `LCOS_Layout_Inventory_v86.xlsx` is already an output, written from scratch by `tools/wiring/write_inventory.py`. But scripts still read spreadsheets as input:
  - `www/scripts/build_wiring_json.py` builds `wiring-inventory.json` from v86, and `signal-splits.json` from `signals_split_v8.xlsx` with the frozen v85 lamp pins.
  - `tools/wiring/create_wiring_schematic_ppt.py` builds `Wiring_Schematic.pptx` from v86.
  - v86's **Power District** column is empty in all 81 rows. Power districts exist only on the hand-drawn slides in `Layout Documentation.pptx`.
  - `docs/wiring/terminal_blocks.md` has not been checked against the railroad.

## Decision

1. **Masters stay in git as CSV or JSON.** Every kind of record has one master file. The copies are built from it, or are outside tools that phase 2 reconciles. A spreadsheet, slide deck or JSON for the site is never a master: it is written from the masters, or it is frozen history.
2. **A catalogue says which file is the master.** `docs/data/entities.csv` has one row per kind of record: the key, the master file, the copies in the repo, the outside tools that hold it (STS, Operations Pro, JMRI, DecoderPro) and which side wins during a session. It names kinds of record. File-level lineage stays in the pipeline map.
3. **Every master file has a column sidecar, and `check.sh` validates it.** `<name>.columns.csv` sits beside the master. It extends the existing format with `type`, `required`, `key` and `refs` (the `file.column` a value must exist in). One step in `tools/pipeline/checks.toml` (`data-schemas`) finds every sidecar by glob. A new sidecar is checked without anyone editing the manifest.
4. **Keys.** Every record has a key that is assigned once and never reused. The key does not depend on row order or on a public name. Where a file already has one, it stays: device `id`, `switch` and `half`, wiring `id` (`switch:35`), `mast`, block `id`, LCOS `node`, car `roster_id` with its pinned STS id (ADR-013), loco `roster_id`, waybill `card_id`. New keys:
   - **industry**: `industry_id`, used by spots, waybills, the routing matrix and `industries.json`.
   - **spot**: `industry_id` plus spot number.
   - **train or job**: the train symbol (`R23A`, `D749`), used by `hart_trains.csv`, `crew.json` and the Operations Pro trains.
   - **location or station**, and **control point**: one id each. Today `stations.csv`, `interlockings.csv` and the devices' `cp` each name them their own way.
   - **block references** use the block `id`, not the public name, starting with `occupancy_bindings.csv`.
   - **power district**: a new kind. The owner supplies the districts; nothing is drawn from the slides by guess.

   Values that are lists of words, not records (commodity, car type, flow), get an allowed-values list in their sidecar. They do not get a key.
5. **Inputs come off the spreadsheets.**
   - `build_wiring_json.py` and `create_wiring_schematic_ppt.py` read the wiring model (`hartlib.wiring`, the one `write_inventory.py` uses), not v86.
   - The frozen v85 lamp pins and the `signals_split_v8` route matrix are exported once to CSV. `signal-splits.json` is built from the CSV, and the owner keeps the old data.
   - The routing matrix's three sheets become CSV masters under `ops/hart-ops/industries/`. The xlsx is written from them.
   - `signals_asbuilt_abs_v2.xlsx` and `lcos_signal_manager_config_plan.xlsx` stay as they are: the first is frozen history, and the second is already written from scratch.
6. **Phase 2, not started here:** drift reports per kind of record (repo against STS, Operations Pro and JMRI), the direction each field flows (session state back from the tools, design data out from the repo), a read-only SQLite built from the masters for queries across files and for the site build (built, not committed, per ADR-036), and a database as master. A database becomes the master only once several people edit records at the same time through a form or the site. `serve_portal.py`'s edit API for `archive.json` and `gallery.json` is the first case to watch.

## Parallel work

Phase 1 runs as parallel lanes, and a lane owns its files. The [project page](../projects/data-masters.md) lists them.

- **Shared files have one owner.** Only the validator lane edits `tools/pipeline/checks.toml`, `check_stamps` declarations and the pipeline map for the `data-schemas` step. It branches after the open ADR-037 stage 4a PR (#1129) merges, and rebases if another PR changes the manifest first. Later lanes add sidecar files and edit only their own masters and readers.
- **Order.** The catalogue lands first: the key lanes need its master choices. The validator and wiring lanes then run together. Key lanes start after the validator merges, so each one lands its sidecar with its keys and is checked in the same PR. Lanes that touch `tools/schematic/`, `tools/hartlib/` or the CATS builders go to `schematic-builder`, take `/code-review high`, and wait for any open schematic or naming PR that changes the same files.
- **Coordination.** The main session holds the `Claimed:` line on the project page and updates the lane table after each merge. Lane agents do not edit the project page, this ADR or `wiki/STATUS.md`. Each writes status lines to the progress file its brief names (handoff skill).
- **Capacity.** At most three lane agents run at once. Before each launch, count the sessions against the cap of 8 in AGENTS.md.

## Consequences

- A wrong reference (a spot naming an industry that is not in the master, a binding naming a block that does not exist) fails `check.sh` instead of surfacing in a session.
- Renaming an industry, station or block changes one row, not every file that spells it out.
- Several readers change in the key lanes: `bin/cars`, the card pipeline, the site build scripts and the CATS builders. Each lane updates its readers in the same PR.
- Power districts stay empty until the owner gives them. The v86 column and the site's layout docs fill in from the master once it exists.
- The DecoderPro roster on the Pi stays outside the repo until phase 2 decides whether it is a copy or a master.
