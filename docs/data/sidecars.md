# Column sidecars

A sidecar `<name>.columns.csv` sits beside a master CSV, describes each of its columns, and gives the rules `tools/ops/check_data.py` checks it against.

The rule is decision 3 of [ADR-039](../../wiki/decisions/ADR-039-data-masters-in-git.md). The `data-schemas` step of `tools/check.sh` runs the checker on every sidecar it finds, so a new sidecar is checked without a change to `tools/pipeline/checks.toml`.

## The sidecar's columns

One row per column of the master, in the master's order. The master's header must be these column names, in that order.

| Column | Meaning |
|--------|---------|
| `column` | The master column the row describes. Required. |
| `file` | Only for a pair master: the file that holds the column, `field` or `generated`. `hartlib.devices` checks it. |
| `description` | What the column holds, for people. Required. |
| `type` | `str`, `int`, `float`, `bool` (`yes` or `no`), `enum` (one of `values`) or `id-list` (items separated by `;`, none empty or given twice). |
| `required` | `yes`, or a condition: the cell is non-empty on every row, or on the rows the condition picks. |
| `key` | `yes`, or a condition. The columns with the same `key` cell form one key: on the rows the condition picks, each of them is non-empty and together they are unique. |
| `refs` | `path/file.csv:column` from the repo root, several separated by `;`. Each value, or each item of an `id-list`, is in one of those columns. |
| `values` | The allowed values of an `enum` column, separated by `;`. Only an `enum` column has them. |

An empty rule cell means no rule. A sidecar may leave off any rule column; only `column` and `description` must be there.

A condition is `col=v1;v2`: the rows whose `col` is one of the values. `col=` picks the rows whose `col` is empty. So `level=2;3` in `required` means required on main and upper, and two keys with the conditions `level=1;2;3` and `level=` key the rows with a level one way and the level-less rows another.

## Which file is the master

The master is `<name>.csv` beside the sidecar. When there is none, it is the pair `<name>_generated.csv` and `<name>_field.csv`, merged as `hartlib.devices` merges the device master: each field row is matched by its key to a generated row and its non-empty cells win, and a field row with no match is added. A field row is added only under a key that no generated row has, such as a Store's level-less rows. Under any other key it is a stale row, and the check fails. The rules run on the merged rows.

A `refs` path names a master the same way: `jmri/layouts/hart/data/devices.csv:user_name` reads the merged device pair, so a name the owner gave in `devices_field.csv` counts.

## Running it

```
python3 tools/ops/check_data.py                       # every sidecar in the repo
python3 tools/ops/check_data.py path/x.columns.csv    # one sidecar
```

It finds sidecars with `git ls-files` (tracked, or untracked and not ignored) and leaves out `archive/`, `external/`, `reference/`, `node_modules/`, `tools/cats/src-repo/` and every folder whose name starts with a dot. It prints each problem with the file, the rule and the rows (up to 20 per rule), and exits 1 when any sidecar fails.

## The sidecars today

- `jmri/layouts/hart/data/devices.columns.csv`: the device pair `devices_generated.csv` and `devices_field.csv`. Keys: `level` and `id` on rows with a level, `layer` and `user_name` on a Store's level-less rows. `detector` is required on every occupancy row; the two spare detectors (`spare:M2S201`, `spare:M2S307`) are `none` (owner, 2026-11-25), which `build_device_map.py` writes for every spare. Its `cp`, `blocks`, `protects`, `part_of`, `facing` and `switch` must name stations, control points, devices and switches that exist. Each `cp` item is a `station_id` or a `cp_id`; `hartlib.places` gives readers the names and writes the ids back, and does the same for the `cp` column of `schematic/masts.csv`. A turnout row has no `cp` (owner, 2026-11-25): its place is its switch's in the switch lists of `stations.csv` and `interlockings.csv` (`hartlib.places.switch_place`), and `hartlib.devices` stops on a turnout row with one. `cats_discipline` (`CTC` or `YARD`) is the owner's cell on the 45 block rows the CATS desks bind (moved from `cats/data/occupancy_bindings.csv`, 2026-11-25); `hartlib.devices` also holds it to block rows, and `hartlib.occupancy_bindings` gives the desk builders and the audits those blocks with their occupancy sensors.
- `jmri/layouts/hart/data/schematic/stations.columns.csv`: `stations.csv`, the station master. Key: `station_id` (`st:barn`, `st:west-yard`).
- `jmri/layouts/hart/data/schematic/interlockings.columns.csv`: `interlockings.csv`, the control point master. Key: `cp_id` (`cp:107`, `cp:east-end`). Brick, Barn, East End and Princess have a row in both files: the station names the staging desk area and its CATS plate, the control point is the signal rule's group of switches. A staging `cp` cell names the station.
- `jmri/layouts/hart/data/block_lengths.columns.csv`: `block_lengths.csv`, each JMRI block's length in the AnyRail plan (`level`, `id`, `plan_in`, `note`), written only by `tools/schematic/plan_lengths.py`. Key: `id`, a device of the master. It holds no names: `hartlib.block_lengths` gives each block its name and occupancy sensor from the device master.
- `jmri/layouts/hart/data/block_lengths_measured.columns.csv`: `block_lengths_measured.csv`, the lengths speed matching measured (`id`, `measured_in`, `run`, `date`, `note`), written only by `infer_block_lengths.py --apply`. Key: `id`, a row of `block_lengths.csv`. `hartlib.block_lengths` gives the plan length and the operating length (measured where there is a row, else plan); `tools/hartlib/tests/test_block_lengths.py` fails a reader that takes the other side's length.
- `jmri/layouts/hart/data/switches.columns.csv`: `switches.csv`. Keys: `half` on main and upper, `os_id` on staging. Staging's ids must name devices that exist, `area` must be an area of `schematic/lcos_nodes.csv`, and an `owner` hand must be given. The file holds no names: `hartlib.railroad_facts.read_switch_rows` gives each staging row the name store's names of its ids.
- `ops/hart-ops/data/industries.columns.csv`: `industries.csv`, the industry master. Key: `industry_id`.
- `ops/hart-ops/data/spot_assignments.columns.csv`: `spot_assignments.csv`, the spot master. Key: `industry_id` and `Spot #`. `industry_id` must be in `industries.csv`.
- `ops/hart-ops/data/HART_Spot_Waybills.columns.csv`: `HART_Spot_Waybills.csv`. Key: `card_id`. `traffic` is `industry` or `interchange` (a car going straight between Scully Yard and Demmler Yard); `industry_id` is required on industry traffic and must be in `industries.csv`, and `usage` must be a usage in `spot_assignments.csv`.
- `ops/hart-ops/data/locos.columns.csv`: the loco master `locos.csv`. Key: `road_name` and `road_number`. `roster_id` is formatted from them (`CSX 2121`, `locos.loco_roster_id`), and the check fails one that is not. `loco_type` is `Diesel`, `Steam` or `Electric`. `tools/ops/check_locos.py` (the `loco-refs` step) checks that both Operations Pro engine rosters and the train list name only locos in it. The owner's answers (2026-11-25): BO 4536, 5300 and 5496 stay as they are; the streetcar is PRC 4678, in this master and in the car master `image_metadata.csv`; Percy (NWR 06) stays. `dcc_address` and `long_address` are the DecoderPro roster's (`jmri/layouts/hart/roster/`, the ADR-039 amendment of 2026-11-26) for every loco it has: `tools/ops/check_roster.py --write` writes them and `make roster-pull` runs it, and the `roster-locos` step fails a roster id that is not a `roster_id` here or a row whose address differs. A loco not yet in the roster keeps the address typed for `bin/cars locos publish`.
- `ops/hart-ops/data/trains.columns.csv`: `trains.csv`, the train master. Key: `train_symbol`. `font` and `runs_job` take the values CATS writes. `on_desks` is `yes` for a train on the CATS desks' train list and `no` for an Operations Pro train only: the staging trains STG-DEMMLER and STG-SCULLY (owner, 2026-11-25), which need no name, engine, font or `runs_job`. `hart_trains.csv` and the desk header hold only the `yes` rows. `tools/audit/check_train_symbols.py` checks the copies that name trains (crew jobs, Operations Pro trains, the CATS desks' train list), and `cats/scripts/build_hart_trains.py` writes `cats/data/hart_trains.csv` from it.
- `www/scripts/archive_catalogue.columns.csv`: `archive_catalogue.csv`, the archive catalogue. Key: `id`. `collection` is `archive` (an item of `www/data/archive.json`) or `logo` (a logo file: every file under `ops/hart-ops/operator_logos/` and the site's own, so the catalogue is the one place for logo credits and `operator_logos/SOURCES.md` points to it, owner 2026-11-25); `derived_from` must be another row's `id`. An archive row's `title` and `caption` are the Photos page's. `www/scripts/archive_catalogue.py` (the `archive-catalogue` step) checks that each archive item's file, title, caption and credit fields are its row's, and `serve_portal.py`'s edits write both, and that each lineage card's `logo_id` names a logo row whose `path` is its `logo`. `tools/ops/check_fleet_gallery.py` (the `fleet-gallery` step) checks `www/data/fleet-gallery.json` against the car master `image_metadata.csv` and the loco master `locos.csv`.
- `www/scripts/layout_docs_labels.columns.csv`: `layout_docs_labels.csv`, the Layout documentation page's label for each detected section (`Yard track Y1`, `Passing siding`). Key: `id`, a device `id`. It is page text, not a fact about the block, so it sits with the site's other data in `www/scripts/` and not in the block master. `www/scripts/build_layout_docs.py` reads it and stops on an ID that is not a detected section, and on a detected section other than an OS block that has no row.

- `jmri/layouts/hart/data/schematic/block_overrides.columns.csv`: `block_overrides.csv`, the owner's hand facts about blocks (`split`, `track`, `crossover_half`). Its switch columns must be switches of `switches.csv`, and `block` a device `id`. A split row is keyed by its two switches, a crossover half by its block ID. `hartlib.hand_lists.read_block_overrides` checks the shape of each kind.
- `jmri/layouts/hart/data/schematic/block_numbering.columns.csv`: `block_numbering.csv`. Key: `id` on live rows, which must be a device `id`, and `retired` on retired rows. `hartlib.block_numbering` checks the rest (one of `numbered_as` and `append_order`, an `append_order` without gaps).
- `jmri/layouts/hart/data/schematic/main_lines.columns.csv`: `main_lines.csv`. Key: `sheet` and `line`. `sheet` is the schematic sheet, `staging` or `main_upper`. Its stops name tracks by block ID inside a stop (`35@block:33A-35A`), which `hartlib.hand_lists.resolve_stop` checks, not a ref.
- `jmri/layouts/hart/data/schematic/retired_virtual_masts.columns.csv`: `retired_virtual_masts.csv`. Key: `mast`. `hartlib.hand_lists.read_retired_masts` checks that no two system names share an ordinal.
- `docs/wiring/lcos/lcos_signal_logic.columns.csv` and `lcos_signal_plan_notes.columns.csv`: the two hand lists `tools/wiring/build_lcos_signal_manager_plan.py` reads. Key: `mast` and `head`, and each mast must be in `schematic/masts.csv`. The build checks that both files hold the same heads as `wiring.csv`, and that each turnout and detector the notes name is in `tables.xml`.

Four hand-kept JSON files that builds read have no sidecar. `tools/ops/check_json.py` (the `json-schemas` step) checks each against a schema of the keys, types and values its readers depend on, and names the file and the key path of each problem: `schematic/plan_overrides.json` and `schematic/preferences.json` (read through `hartlib.layer_files`), `schematic/panel_items.json` (read by `tools/schematic/panel_items.py`, which also parses each item's XML) and `www/scripts/published-files.json` (each source must be a file). `tools/audit/tests/test_check_json.py` tests it. The other hand-kept JSON files (`sts_jmri_ops_settings.json`, `party_logo_map.json`, `provenance.json`, `share-cards.json`) have a row in `entities.csv` and no schema here.

The crew master `ops/hart-ops/data/crew.json` has no sidecar: it is nested JSON (jobs with steps, sequences and lineups, maps with tracks), which these columns cannot describe. `ops/hart-ops/publications/crew_schema.py` checks it instead (unique job codes and color ids, required fields, each job's colors and maps, each map's connections and sheets, each spot sheet industry in `industries.csv`, and the fields a `docx` object may hold), and `build_crew_json.py` runs that check before it writes `www/data/crew.json` (the `crew-json` step). `ops/hart-ops/tests/test_crew_master.py` tests both.

`www/scripts/tests/test_industry_ids.py` checks what a ref cannot: that each spot and waybill's name matches its `industry_id`, that a waybill's spots are spots of its industry, and that `www/data/industries.json` lists each industry once, under its `public_name`, `slug` and `blurb`, with the waybill count and commodities of its waybills. Its one interchange entry has no `industry_id` and carries `category: "interchange"`.

### Owner decisions (2026-11-25) and what is left

- `name` is the Operations Pro spelling (`A. Stucki Co.`, `Ferrellgas`). The name columns of `spot_assignments.csv` and `HART_Spot_Waybills.csv` keep the old spellings (`A Stucki Co`, `Ferrel Gas`), because the STS seed in `external/sts-helpers` has them in its code. One later follow-up renames them together with sts-helpers and deletes the test's alias list.
- Interchange is a kind of traffic, not an industry, so it has no row. Its site entry's `spot` is `interchange` (owner, 2026-11-25); `scully` is Scully Yard's own spot sheet.
- The Aristech and Ferrellgas blurbs follow the Operator Sheet's traffic lines (owner, 2026-11-25): pellets and process chemicals in, resins out, served by NVL; LPG in, empty tanks out.
- Follow-up, not done yet: the `Industry` column of `spot_assignments.csv` and the `industry` column of `HART_Spot_Waybills.csv` drop once an `external/sts-helpers` change makes its STS seed read `industry_id`; the alias list in `test_industry_ids.py` goes with them.
- `generate_waybill_cards.py` renumbers `card_id` from 1 when it runs and rewrites `HART_Spot_Waybills.csv`, so it is not to be run against the master until a later decision. Live waybills and the print queue are tracked in STS.
