# hartlib

The shared library for the repo's CPython tools: one way to read and write `tables.xml`,
one place for repo paths, one place for broker and JMRI host settings, and the name
map's DCC column. Standard library
only, Python 3.9 or newer.

**Never import hartlib from a Jython script that runs inside JMRI** (JMRI runs Jython 2.7).
That covers `jmri/scripts/signal_coordinator.py`, `jmri/layouts/hart/scripts/panel_status.py`
and every other script that does `import jmri` or `import java` (about 20 of them sit among
the CPython scripts in `jmri/layouts/hart/scripts/`). Leave `jmri/scripts/check_hart_phase02.py`
alone too.

## How a script finds it

hartlib is not installed. Each script puts this checkout's `tools/hartlib/src` first on
`sys.path` with the same two lines (after `import sys` and `from pathlib import Path`):

```python
sys.path[:0] = [str(p / "tools/hartlib/src") for p in Path(__file__).resolve().parents
                if (p / "tools/hartlib/src").is_dir()][:1] or sys.exit(f"no tools/hartlib/src above {__file__}")
from hartlib import paths, tables  # noqa: E402
```

They walk up from the script, so moving a script to another folder needs no edit. Outside
a checkout the script stops with `no tools/hartlib/src above <script>`.

Why not `pip install -e`:

- Plain `python3` is Homebrew's, which refuses `pip install` (PEP 668). `tools/check.sh`
  also runs the root `.venv` and `ops/hart-ops/.venv` interpreters, and CI a fresh one.
  The lines above work in all of them with no install step, and in a fresh clone.
- Agents work in worktrees. An editable install points at one checkout, so a worktree's
  script would import the main checkout's hartlib and read the main checkout's tables.xml.
  The lines above always load the copy next to the script, ahead of any installed copy.
- `hartlib.paths` finds the repo from its own file. A copied (non-editable) install has no
  repo around it, so its import fails with a message saying so. `hartlib.hosts` does not
  need the repo and imports anywhere.

`pyproject.toml` exists for editors and linters only.

## API

### `hartlib.files`

`write_atomic(path, text_or_bytes)` replaces a file through a temporary file in its folder and `os.replace`, so a
reader or a stopped run sees the old file or the new one. It keeps the old file's mode. By default (`Tables.save`) it
writes through a symlink and rewrites a hard-linked file in place, which is not atomic; `follow_links=False` replaces
the path itself and leaves other links on the old file. `tracked_files(root, *pathspecs, submodules=True)` is
`git ls-files` (with `submodules=False`, submodule entries left out; `manifest_base.py` keeps its own copy, as the
manifest loads no module from outside its folder) and raises `GitError` when git cannot list them.
It never walks the folder instead, which would find untracked and ignored files.

### `hartlib.film_pace`

`STEP_S` (0.4) and `FINAL_HOLD_S` (2.0), the pace of the four films on `www/behind/panel-evolution.html`; `durations(n)` and `film_length(n)`. Used by `tools/schematic/evolution.py` and `tools/ctc_history/films.py`.

### `hartlib.paths`

Every path names a file in **this** checkout, the one hartlib sits in. `HART_REPO_ROOT`
and `HART_RUNTIME_ROOT` (exported by `tools/env/load_env.sh`) do not move them, so a
worktree never reads the main checkout's tables.xml.

| Name | Path |
|------|------|
| `REPO_ROOT` | the checkout |
| `JMRI_DIR` | `jmri/` |
| `LAYOUT` | `JMRI_LAYOUT`, default `hart` (a single-layout setting; only `hart` exists) |
| `LAYOUT_DIR`, `LAYOUT_DATA`, `LAYOUT_OUTPUT`, `LAYOUT_SCRIPTS` | `jmri/layouts/hart/` and its `data/`, `output/`, `scripts/` |
| `TABLES_XML` | `jmri/layouts/hart/output/tables.xml` (ADR-008), or the file `HART_TABLES` names |
| `REPO_TABLES_XML` | always `jmri/layouts/hart/output/tables.xml` |
| `DEVICES` | `jmri/layouts/hart/data/devices_generated.csv`, the device master's handle (`hartlib.devices` merges `devices_field.csv` beside it) |
| `WIRING` | `jmri/layouts/hart/data/wiring.csv`, the physical wiring source (`hartlib.wiring`) |
| `CATS_DIR` | `cats/` |
| `JMRI_USER_FILES` | `~/JMRI_UserFiles` (ADR-014) |

Functions: `lcos_bridge()` (the submodule, else a sibling clone), `car_images_final()`
(`HART_CAR_IMAGES_FINAL`, else the repo copy), `rel(path)` (a repo-relative string for
messages). `layout_paths()` replaced `jmri/layout_paths.py`; its one live
caller is `jmri/scripts/generate_nx_pairs.py` (parked with NX), and the AnyRail-era scripts that used the rest
are in `archive/code/jmri-scripts/`.

`HART_TABLES=<file>` (checks only) points `TABLES_XML` at another tables file, such as the Layout Editor cut-over candidate: `HART_TABLES=<file> tools/check.sh` runs every table check against it, and the unit tests still read the checkout's file. The file must exist and lie outside `~/JMRI_UserFiles`. Nothing is written while it is set: `Tables.save` refuses the checkout's tables.xml, the override and anything in the profile, every other script that writes tables, the profile or an output derived from the tables calls `paths.exit_if_overridden(name)` first, and the deploy and PanelPro wrappers stop through `refuse_hart_tables` in `tools/hosts/profile_tables_guard.sh`.

### `hartlib.tables`

```python
doc = tables.load()            # this checkout's tables.xml, or load(path)
root = doc.root                # an ElementTree element; edit it in place
doc.changed()                  # bytes differ from what was loaded?
doc.save()                     # writes only if the bytes differ; returns True if written
root = tables.read(path)       # read-only scripts: just the root
```

A load followed by a save with no edit is byte-identical, for the repo file and for a raw
PanelPro Store. The bytes outside the root element are kept verbatim, comments inside it
are kept, and characters are escaped as JDOM (JMRI) escapes them: `&#xD;` for CR in text,
`&#xD;` / `&#xA;` / `&#x9;` in attributes. A file ElementTree wrote with its own forms
(`&#13;` / `&#10;` / `&#09;`) keeps those. `save` replaces the file through a temp file and
`os.replace`, keeping its mode; a symlink is followed and its target written, and a
hard-linked file is rewritten in place. A running PanelPro or CATS does not stop it: JMRI changes `tables.xml` only on a Store.

Lookups (all take the root element unless noted):

| Function | Returns |
|----------|---------|
| `turnouts`, `sensors`, `signal_heads` | every bean across all manager sections |
| `masts(root, tags=MAST_TAGS)` | `<signalmast>` and `<virtualsignalmast>` in file order |
| `blocks(root, full=True)` | the full `<block>` pass (`full=False`: the names-only pass) |
| `layout_blocks` | `<layoutblock>` beans |
| `layout_editor(root, name=None)` | the main Layout Editor panel, or the one named |
| `layout_editors` | every Layout Editor panel |
| `generated_panel(panel)` | True when the panel holds the hidden marker label a generated panel carries (`build_layout_le.build`, written by `build_tables.py`); two markers raise ValueError |
| `generated_marker_label()`, `GENERATED_PANEL_MARKER` | that label and its text |
| `require_generated(panel, what)`, `require_generated_panel(root, what)` | the (main) panel when it is a generated one; else ValueError naming `what` |
| `ensure_block_contents_visible(le, check=, spots=)`, `BCI_*` | block contents labels on level 4 in black, the plugin's font kept, optionally at given spots |
| `layout_turnouts(panel)` | `<layoutturnout>` (turnouts and crossovers) on a panel |
| `continuing_sense(lt)` | `CLOSED` (2), `THROWN` (4) or `UNKNOWN` (1) |
| `mast_logics`, `mast_logic_sources`, `mast_logic_pairs` | SML elements, source -> element, (source, destination, element) |
| `system_name(el)`, `user_name(el)`, `text(el, child)` | stripped names and child text |
| `by_system_name`, `by_user_name`, `by_any_name` | dicts over any list of beans |
| `section(root, container, tag)`, `elements(el)` | generic: all sections; children without comments |
| `remove_child(parent, child)` | take a child out, keeping the indentation of what follows (the build's strip and `hartlib.parked`) |

### `hartlib.wiring`

`jmri/layouts/hart/data/wiring.csv`, the physical wiring source (owner, 2026-11-20): one row per device on an LCOS
node. `wiring.read()` gives checked `Wire` rows; `w.address` is the JMRI system name (M2T408, M2S470, IH432, M2S1300)
and `w.wiring_text` the wiring text the device master and the JMRI comments carry ("Node: 4 Turnout: 0 | OU: 1 Ports: 1,2").
Staging's rows are as wired in JMRI, plus the fascia buttons, relays and calibration relays, which have no JMRI
device (kinds `button`, `relay` and `calibration`, no index); main and upper's are the detectors the owner placed (planned), the rest of those levels being
given out by `build_device_map.py`'s rule. A device row is keyed by its device ID (`id`: switch:35, fb:35:N, a head's
mast:5:B:west:single, a detector's det:<block id>; naming-layers step 5) and holds no name: `read()` gives `w.device`
the name store's name (`devices.user_names`, a detector's its block's) and `w.id` the ID, so a rename in
`devices_field.csv` changes no row and the frozen pins stay. Only a button's, relay's or calibration relay's label is
in `device`; a main or upper track detector keeps its plan key (switch_a, switch_b, parallel, half).

### `hartlib.hand_lists`

The one reader of each of the owner's hand lists (naming-layers step 6); each stops with `HandListError` (a
`ValueError`) naming the file and line. `read_block_overrides(path, kinds)`: `block_overrides.csv`, every level's
rows keyed by switch numbers, a track row's `block` an OS block ID given back with its generated name
(`os_block_name`) and the ID in `id`; `mast_rule.read_block_overrides` wraps it (a `MapError`). `read_main_lines(sheet,
path, names)`: `main_lines.csv`, each stop's block IDs named from the name store (`resolve_stop`);
`build_main_route.read_lines` wraps it (a `RouteError`). `read_mast_cells(data)`, `read_uss_cells(data)` and
`read_uss_plants(data)`: the parked USS CTC board (`mast_cells.csv`, `uss_board_cells.csv`, `uss_board_plants.csv`);
`layout_facts.py` re-exports them as `load_mast_cells` and the others. Step 13 added three: `read_retired_masts(path)`:
`retired_virtual_masts.csv`, `{mast: system name}` of the dropped virtual masts, each ordinal once
(`mast_plan.read_retired` wraps it, a `MapError`); `read_sheet_rows(path)`: `sheets.csv` as `(line, row)` pairs
(`railroad_facts.read_rows`, a `FactsError` on a missing column; `build_staging_sets.read_sheets` checks the cells);
`read_panel_items(path)`: `panel_items.json` parsed (`panel_items.load` checks the items, an `ItemsError`). Their
paths are `RETIRED_MASTS`, `SHEETS_FILE` and `PANEL_ITEMS`.

### `hartlib.hand_tables`

The two inputs of `tools/audit/check_hand_tables.py` (owner, 2026-11-26: anything kept by hand goes in a CSV read
through hartlib). `railroad_names(entities, root)`: `{name or id: "kind (master)"}`, every value of the key column and
the `NAME_COLUMNS` of each CSV master `docs/data/entities.csv` names (a cell's `;` items split, one- and two-character
values and numbers under 100 left out), so a new master adds its names with no change here; `masters()` and
`master_files()` say which files that reads. `read_listed(path)`: `tools/audit/hand_tables.csv` by `(file, table)` as
`Listed` rows (entries, a status of `move`, `unreviewed` or `keep`, and the reason), stopping with `HandTablesError`
(a `ValueError`) naming the file and line; `write_listed(path, rows)` writes it back sorted.

### `hartlib.drawing_keys`

Which device each piece of the drawing is, keyed by device ID (naming-layers step 13, builder merge step 7): the one
reader of the device master's `trial_name` keys for every level. `read(levels, source=None, rows=None)` gives `Keys`:
`ids` ({drawing key: (level, device ID)}, the master's key; "Switch 101A", "OS 7 A-13C", "Track 1B-3A 1/2") and `rows` ({(level, ID): merged row}) of the
turnout and block rows of `levels`, parts among them, no LCC alias; `id(key)`, `row(key)`, `name(key)` (the ID's name in the
merged view: the owner's, else the generated), `keys(id)`, `of(layer, role, parts)`, `parts()`. `DrawingKeyError` (a
`ValueError`) on a row with no key or no id, a key given twice or an id twice on one level, an LCC alias with a key, a part of no block row of its level, or a staging key with a plan "*". Its readers:
`le_names.device_names` (the Layout Editor build's main and upper names), `staging_device_map.load` (staging's, the
device map's masts and the CATS desks' tracks), and `cats_panel.drawn_keys` (the desks' balloon-loop halves and
parts).

### `hartlib.block_numbering`

The main and upper blocks' JMRI numbers (naming-layers step 8, builder merge step 2). `read(path, names)`:
`block_numbering.csv`, its ids named by `names` (default `devices.user_names()`), a `Numbering` of `numbered_as`,
`appended` and `retired` by block name, `NumberingError` (a `ValueError`) naming the file and line. `order(blocks,
numbering, require_listed)`: OS blocks first, then by the number at the end of the name (`block_sort`), a block in
`numbered_as` in the place of the name it replaces, the appended ones last. `bean_names(blocks, numbering)`: `{block:
(IB:C3:<nnnn>, ILB<1000 + nnnn>)}` (`level_devices.BLOCK_PREFIX`, `LAYOUT_BLOCK_FIRST`), the retired blocks holding
their numbers. `build_device_map.block_beans` writes them into every main and upper block row but a helix block's,
numbered over the generated names so an owner's rename keeps them; `le_tables` reads them off the rows
(`level_block_beans`) and keeps the stale-row check (`numbered_blocks`).

`tools/audit/check_data_readers.py` (job `data-readers` in `tools/check.sh`) fails when a script outside hartlib names
a file under `jmri/layouts/hart/data/`, unless its `ALLOWED` table lists the script and file with a reason (a writer of
its own output, a schematic plan input, a stamp hash, a path handed to a hartlib reader, a reader not moved yet);
Jython inside JMRI is held to naming none but the one `JYTHON_ALLOWED` lists. `--list` prints the table.

### `hartlib.railroad`

The railroad's facts in one place: each fact file read once into typed objects, and the rules between the files
checked together. `python3 -m hartlib.railroad check` (in `tools/check.sh`) runs them; `invariants` lists them.

```python
rr = railroad.Railroad()                  # this checkout's files; Railroad(Sources.under(data_dir), upto=...)
rr.switches[9].legs[0].closed             # staging switches (the level 1 rows of switches.csv + the device master)
rr.device_map.occupancy["OS Switch 101"].jmri_name    # IS:HART:C3:B:OS101
rr.check()                                # [Problem(invariant, message)]
```

The files come in **layers**, in the order `tools/schematic/build_panels.sh` makes them: `inputs` (hand-kept:
`switches.csv` (every level's switches, ADR-021), staging's rows of the device master, `interlockings.csv` (every level),
`lcos_nodes.csv`, `plan_overrides.json` (its `main_upper` section), `block_lengths.csv`), `hands` (the main and upper hands of `switches.csv`, which `build_hands.py` writes into its plan rows), `device_map`, `masts` (`schematic/masts.csv`, every level's masts) and `tables`
(`tables.xml`). `Railroad(upto=layer)` raises `LayerError` when asked for a later layer, so a builder never reads a
stale copy of its own output: `build_device_map.py` loads `upto="inputs"`, `build_cats_panel.py` everything.

| Name | What |
|------|------|
| `Railroad.staging_devices` | `StagingDevices`: staging's (level 1) rows of the device master in the device layers, `rows` (`StagingDevice`: the master's own columns), `by_name` ((layer, user name) -> row), `names(layer)` |
| `Railroad.switch_rows`, `switches` | `[SwitchRow]`: switches.csv as read (`read_switch_rows`, every row held to the shape of its key, not its level, naming-layers step 14: `by_os`, a row keyed by its OS block's ID, `os_id`, with its legs' `closed_id` and `thrown_id`, and `os_block`, `closed_leg` and `thrown_leg` the name store's names of those ids, looked up on the read (the file holds no names), as staging's are; else a row keyed by its half, as main and upper's are); `{number: Switch}` of its rows keyed by their OS block (staging's) (`Switch`, `Leg`; `layout_facts.py` re-exports them) |
| `Railroad.interlockings` (every level), `level_control_points` (its main and upper rows), `local_switches`, `lcos_nodes`, `main_upper_switches` | `Interlocking`, `LocalSwitch`, `LcosNode`, `{number: MainUpperSwitch}` |
| `Railroad.plan_overrides` | `PlanOverrides`: `data` (the whole file), `edits`, `relabel`, `helix` |
| `Railroad.block_lengths`, `hands` | `{name: Block}` of `block_lengths.csv` (`hartlib.block_lengths.plan_blocks`: `level`, `id`, `plan_in`, `note`, and the name and `occupancy_sensor` from the device master), `{label: Hand}` |
| `hartlib.block_lengths` | the two block length files (ADR-039 lane L8): `block_lengths.csv`, the plan length that `plan_lengths.py` writes, and `block_lengths_measured.csv`, the lengths speed matching measured (`infer_block_lengths.py`). Plan side: `plan_blocks`, `plan_lengths`, `plan_cm`, `plan_length`, `read_plan` (the drawings, mast and signal placement, the pages). Operating side: `operating_lengths`, `operating_length`, measured where there is a row, else plan (tables.xml, speed matching). `measured_lengths` gives the measured rows to the pages that print them. `tests/test_block_lengths.py` lists the readers on each side |
| `Railroad.device_map` | `DeviceMap`: `rows` (`DeviceRow`, each with its `id` and `assignment`; `swapped` when it is field: a device swapped in by its row, whose occupancy row is held to its wired M2S sensor, naming-layers step 14), `blocks`, `occupancy` (block -> its occupancy row, its detector by ID: `det:<block id>`), `turnouts` (by the switch number of the row's ID, `turnout_switch`), `heads_by_system`, `of(layer)` |
| `hartlib.device_rows` | the device master's row as a record (railroad_facts re-exports it): `MasterRow`, any row of the merged view, and `DeviceRow`, a row with a level (`level` a `Level`). `devices.load()` and `devices.index()` give them; each is also a read-only mapping of the master's columns to their text (`row["level"]` is `"2"`, `row.level` is `2`), for code not yet moved to the attributes. `Switch.level` is a `Level` too |
| `Railroad.masts` | `hartlib.level_masts.read()` rows, every level (`read_masts(path, levels=...)` gives `[Mast]`: line, level, name, blocks) |
| `Railroad.tables` | `TablesNames`: `root`, `turnouts`, `sensors`, `masts` (user -> system), `blocks` |
| `read_*(path)` | each file alone; `FactsError` names the file and line |
| `check_virtual_names(rows, owner_named=(), swapped=())`, `join_main_upper(cps, local)` | the rules `build_device_map.py` builds by; a turnout's number and a block's detector are read by ID (naming-layers step 13), and a device the owner names (`owner_named`: its field row's level and id; the device-map invariant passes them) keeps its generated virtual names, held to their form only; a field row (`assignment` field: a swap by its row, ADR-028; naming-layers step 14, a column test), or one of `swapped`, to no virtual rule |

`KNOWN` in the module lists problems already reported to the owner, each by its exact message: they print and pass,
anything else fails, and a `KNOWN` entry that no longer happens fails.

### `hartlib.devices`

The device master for all three levels (ADR-029) is two files since 2026-11-21 (the amendment):
`devices_generated.csv`, every row the builders make, and `devices_field.csv`, the owner's cells (`FIELD_COLUMNS`),
each row keyed by its device ID on its level (`KEY`: level, id; naming-layers step 4) and holding its layer, plus a
Store's level-less devices in full (keyed by layer and user name; `key_of`). The field `user_name` is an owner's cell
like the rest: it wins over the generated name, and a rename touches no key. `load()` and `index()` merge them (a
non-empty field cell wins; a field row whose ID no generated row has stops, decision 3; a field `jmri_comment` with
`{occupancy}` is the builder's to fill from `wiring.csv`), cached on both files' bytes. `field_index()` is a builder's
one source of the owner's cells, `{(level, id): row}`; `allocated_names()` its one read-back of its own output (the
numbers it gave). `write_generated` and `write_field` are the only text writers; `one_file_copy` and `pair_copy` make
a test's copy. `devices.columns.csv` (`column,file,description`, then the rule columns `tools/ops/check_data.py`
checks, `docs/data/sidecars.md`) describes every column and which file may hold it, and a test holds the two to each
other both ways. Every row with a level carries an `id` (ADR-033): a key derived from
the plan, not from its name, unique on its level (`hartlib.device_ids` holds the grammar). `hartlib.track_names` is
the name store (ADR-033 decision 2, naming-layers step 3): the field block rows with a track ID (`block:...`) and a
name reach the schematic plugin's `name` and `end` edits and `left_end` when `layer_files.view` merges the plan view,
each track found in the plan graph by its ID's switch labels and legs, so `plan_overrides.json` holds no track name
(`track_names.hand_problems`, which every merge runs). `preferences.json` and `stations.csv` name tracks by block ID
too (naming-layers step 5b): the preferences' track keys (`min_cells` track names, `turnbacks`, `track_labels` keys,
and the label options `extra_steps`, `extra_follow`, `name_columns`, `name_steps`, `optional_block_contents` and
`hidden_names`) get their names in the merged view (`layer_files.merged(data, "preferences")`, through
`track_names.pref_section`), and `track_names.pref_problems` stops a hand section that names a track or holds a
"Track ..." string; `stations.csv`'s `tracks` cell is block IDs, named by `railroad_facts.station_tracks`.
`track_names.names_by_id` answers both, matching each ID on its sheet's or station's level: the owner's name in
`devices_field.csv`, else the generated one in `devices_generated.csv`. That file is the device-map step's output, so
the view keeps an ID with no name yet as it is, and `layer_files.unnamed_preferences`, run by the device-master
check after device-map, stops on one. Staging, main and upper are one structure, a level differs in
column values only. Every reader gets its rows from here (R9b-2, 2026-11-20): `load()` (the master rows) and
`device_map_lines` (the old device-map rows of some levels, plus `role`); `comment_of(row)` is a row's JMRI comment.
The two device maps and `public_name_map.csv` are gone (R9e, 2026-11-20), and so are the six `pnm_` columns that kept
the name map's copy (2026-11-21): their facts are in `cp`, `system_name`, `dcc`, `wiring`, `jmri_comment` and
`notes`. Readers test `role`, never a name prefix.

- `assignment` is `field`, `virtual`, `none` or `spare`; `role` says what the device is; `written_by` is a script in
  `devices.WRITERS` (the one list) on every row with a level, empty only on a Store's level-less row. A writer
  replaces only its own rows and stops, naming the row, on an ID or a name someone else holds.
- `load()` reads and checks once per file state; `check_rows` holds the invariants (a name and an id unique on their
  level, written_by and assignment in their sets, field rows `system_name == jmri_name`, order, one comment per row, a
  description on every row). Row order is level, layer, then each writer's; a Store's level-less rows come last.
  Messages name a row by its name (`row_text`, `at(row)`: "devices_field.csv: Track 12 (level 1, block)"), never a
  line.
- Writers call `outputs_after(writer, old_form_rows)` (or `outputs_after_rows` with master rows) and write the texts it
  gives: the generated file's text, the field file's cells left empty (`unmerge`; the id and user name stay, so the
  generated file names every row). It refuses a row that overrides a field cell, a name other than the field row's
  (that builder does not take the owner's name), or drops an ID the field file holds cells for. Nothing is written
  until every check has passed.
- `hartlib.device_changes` holds each write to the last generated file by ID and says what changes (to stderr, or a
  `warn` callable): the new and gone IDs per level and layer; a gone ID with owner's cells stops (decision 3), listing
  the new IDs of its level and layer; a rename lists the lines of the repo's Operations Pro files that hold the old name
  (decision 5; nothing rewrites them, STS is not checked); a mast rename warns that it needs a new SML discovery and the
  owner's panel approval (decision 6).
- `user_names()` is the name store's `{(level, id): user name}` of the merged view, the one way a file keyed by ID
  (wiring.csv, block_lengths.csv, switches.csv's staging legs, block_overrides.csv, block_numbering.csv,
  main_lines.csv; naming-layers step 5) gets its names; `name_of` stops on an ID the master does not have (decision 3).
  The merge follows a block's rename in the field file into the generated cells that name it (`BLOCK_REFS`: part_of,
  blocks, facing, protects; `follow_renames`), so the view stays whole between the owner's edit and the next build.
- `python3 -m hartlib.devices check`. Errors are `DevicesError` (a `FactsError`).
- One row path for every level (naming-layers step 7; `FIELD_LEVEL` is gone): the builder makes each device's row
  from the plan (staging's switches from the plan graph, `track_names.plan_switches`) and puts the device's field row
  over it by id (`device_map_rows.owner_over` in `tools/schematic/`), so the owner's name and values win on every
  level and a device with no field row keeps the generated values (a staging block is numbered as a part is, a
  staging turnout is bound to its address). A turnout, alias or feedback row's `wiring.csv` row is found by its id (an
  alias by its turnout's), and `wiring.read` names a staging turnout or feedback with no owner's name by its id
  (Switch <n>); a spare detector is `wiring.csv`'s alone. Staging's nodes are as built: a staging device with no
  `wiring.csv` row stops. Staging's masts and heads are `build_device_map.py`'s too since step 12
  (`device_map_masts.py`): every level's mast and head rows have one writer, their field rows and wired heads are
  found by ID, and a mast's field `user_name` (the owner's name) names its heads.
  A line block (`LINE_ROLES`) and its sensor list in `cp` the places it joins, `;` between (`build_device_map.line_cp`); any other row has one control point at most, and `check_rows` holds it.
  A turnout row (its LCC alias's too) has no `cp` (owner, 2026-11-25): the switch lists of `stations.csv` and
  `interlockings.csv` are the one place for the switch-to-place link. `places.switch_place(level, n)` gives a switch's
  place id (staging's desk area as its naming station's id, main and upper's interlocking, "" for a local switch), and
  `devices.place(row)` (`places.of`) a row's place by name: its `cp`, a turnout's from the lists. `device_map_lines`,
  `railroad_facts.read_staging_rows` and `describe` give a turnout that place; `check_rows` stops on a turnout `cp`.
- A device's kind comes from its row, never from its name (hand-off row 8): `row_role(row, where)` is a row's `role`
  and stops with a `DevicesError` naming `where` (file and key) when the row has none; `is_os(row)` says whether a block
  or occupancy row runs through a switch's points (`OS_ROLES`: `os`, `xover_corner`). A reader that holds only a name
  uses `index()`, the master by (layer, user name), built once per file state: `rows(layer, name)` (one per level the
  device is on; a helix block has two), `role(layer, name)` (stops when the rows disagree, naming them),
  `is_os(block)`, `names(layer, roles=, levels=)` (a role query leaves out a device not on the layout yet, a
  level-less row with no role), `has(layer, name)`, `is_unplaced(layer, name)` and `where(row)` (the row's key and
  file for a message). No reader falls back to a name prefix; a tables.xml bean with no row is
  named in a warning and left out.
  A writer states the role of every row it makes (part B): `master_row` takes it from the row (`role`, one of
  `ROLES`) and stops on a row with none, and `railroad.DeviceRow` has no role default (a row with none stops, naming
  its line). `build_device_map` gives each row the role of what it builds (a line block's from its track's ends:
  `line_role`), and each mast the role the mast rule placed it with (`device_map_masts.device_rows`). A block's occupancy row is
  found by its `blocks` column (`DeviceMap.occupancy`), not by building the sensor's name. Kept on purpose:
  `level_devices.block_key` and `occupancy_user`, the owner's naming rule that builds a virtual sensor's name from
  its block's name (2026-11-17), with the checks that hold the rows to it (`check_virtual_names`, `read_device_map`).
- `layout_block` (block rows) is the block's JMRI layout block (`ILB...`): staging's, which JMRI numbered once; main
  and upper's, `ILB<1000 + n>` beside `jmri_name` `IB:C3:<n>`, which `build_device_map.py` copies from
  `block_numbering.csv` (`hartlib.block_numbering`, naming-layers step 8) and `tables_build.master_beans` names the
  beans by (the Layout Editor build holds the drawn blocks to the numbering, `le_tables.check_level_blocks`). Those rows
  are `assignment` virtual (`IB:C3:` is in `SOURCE_PREFIXES`); a helix block's main or upper row has neither name,
  its beans are staging's. A wired head's comment is its `wiring`.
- `start` and `bean_comment` (naming-layers steps 9 and 11): what a main or upper bean takes from its row beyond its
  names. `start` is the state a virtual bean takes when the tables load (`devices.START` by layer: inactive on a
  detector, closed or thrown on a turnout; `level_devices.START_ENUM` gives the JMRI word for the startup LogixNG);
  `bean_comment` is the bean's JMRI comment in staging's form (owner, 2026-11-23): the parts joined by " | ", the
  place first, a block's detector first, `level_devices.VIRTUAL_NOTE` ("internal, not wired") on a bean no field
  device drives, then `level_devices.planned_note` (the planned device, a draft). `build_device_map.py` writes both
  (`device_map_rows.bean_cells`); staging rows leave them empty, their comment is `tables_build.bean_comment`'s.
  `tables_build.master_beans` reads both.

### `hartlib.tables_build`

`tables.xml` is an output (ADR-029, R9c): `tools/schematic/build_tables.py` writes it, and `--check` (in
`tools/check.sh` and `make panels`) fails on any difference. This module holds its parts that come from no drawing:

- `read_template()`: `jmri/layouts/hart/data/tables_template.xml`, what PanelPro owns (settings, memories, the clock
  sensor, the "Hide windows on start" LogixNG), in JMRI's format, every section of `SECTIONS` once and in order, with
  the fixed envelope (`PROLOG`, `EPILOG`) and none of what a Store writes each time (`ENVELOPE_DROPS`).
- `base()`: the template with every level's beans of the device master (`master_beans`, naming-layers step 11) and
  the startup LogixNG around their startup actions (`start_logixng`), each section in JMRI's system-name order
  (`jmri_order`). `build_layout_le.py` draws its panels on it and adds no bean.
- `master_beans(rows, lengths, levels=None)`: each row's beans from its columns alone (naming-layers steps 10 and
  11; `levels` default every level a row has): its layer gives which (`LAYER_BEANS`), `bean_name` the system name
  (`system_name` on a field turnout, else
  `jmri_name`, ADR-028), `row_comment` the comment (`bean_comment` where set, else the wiring columns' `bean_comment()`),
  `turnout_feedback` TWOSENSOR on the turnout's two `fb:<n>:R|N` rows of its level when both give beans and DIRECT
  when neither does on a virtual turnout (a field turnout stops), `alias_is_turnout` no bean for an LCC alias that names its turnout's bean (no turnout row stops), and `start_actions`
  an ActionSensor or ActionTurnout (`start_action`) for each virtual row with a `start`, under `START_ACTIONS`. A
  block takes the detector of its own level that names it; a helix detector binds staging's helix block
  (`HELIX_LEVEL`). `tools/schematic/tests/test_bean_goldens.py` pins every main and upper bean.
- `start_logixng(root, actions)`: the LogixNG that runs the startup actions once when the tables load
  (`level_devices.CLEAR_*`: its ConditionalNG, a DigitalMany with a socket per action), as PanelPro 5.16 stores it.
- `read_discovered()` / `discovered_from_store()` / `write_discovered()` / `merge_discovered()`:
  `data/schematic/discovered_sml.xml`, the Signal Mast Logic and mast properties stock discovery wrote. Only
  `build_tables.py --discovered-from STORE` (run by `run_sml_discover.sh`) writes it.
- `digicon_masts()` / `disable_digicon()`: the Digicon masts' logic boots disabled; the generator applies it, so the
  deploy ships the committed bytes.
- `strip_envelope()`: takes a Store's file history, "Written by" comment, clock time and memory values out;
  `normalise_store()` also drops the block paths JMRI derives from the panel and normalises each Layout Editor
  panel past what a Store rewrites (`normalise_panel`: window state, attribute and element order, numbers at
  float32, a block contents icon's editable flag, a turnout's derived A and D points); it is applied to both sides.
- `jmri_sort()`: every section's beans in the order a JMRI 5.16 Store writes them (by system name), so a load and
  Store gives the generated bytes back. `python3 -m hartlib.tables_build roundtrip --store S --paths P` compares
  a Store with the generated file; `tools/hosts/run_panelpro_roundtrip.sh` runs PanelPro to make one.

Errors are `TablesBuildError`, naming the file, section or row.

### `hartlib.store_split`

The split of a pulled PanelPro Store back into the sources (R9d; `tools/schematic/split_store.py` runs it). It
compares the base (what the host had before the session), the repo's generated `tables.xml` and the Store, all
normalised, item by item (`index`: a bean, a setting, a section's attributes, a Signal Mast Logic, an extra section,
a panel). `plan()` sorts each item the owner changed: KEPT (a template item the repo did not change: the template
takes it), CLASH (the repo changed it too, or there is no base: reviewed), DEVICE (a rename or comment on a hand-kept
device-master row: reviewed, `Edit`s to write) and DROPPED (the build's: the repo wins, with what to change instead).
`new_template()` writes the chosen template items, `edited_rows()` the merged cells, and `verify()` checks a
rebuild gives exactly what the plan promised. `read_template()` accepts an extra section a split kept (a Route
table, say), never a second copy of a known one. Errors are `SplitError`.

### `hartlib.places` and `hartlib.occupancy_bindings`

`places`: the stations of `schematic/stations.csv` by `station_id` (`st:barn`) and the control points of
`schematic/interlockings.csv` by `cp_id` (`cp:107`). The `cp` cells of the device pair and of `masts.csv` hold these
ids; `hartlib.devices` and `level_masts.read` give readers the names (`places.names`), and the writers put the ids
back (`places.ids`, a station's id before an interlocking's of the same name). `occupancy_bindings.rows(files=None)`: the
blocks the CATS desks bind, the block rows of the device master with a `cats_discipline` (CTC or YARD, the owner's
cell in `devices_field.csv`; `cats/data/occupancy_bindings.csv` until 2026-11-25), each with its level, `block_id`,
`block_user_name` and occupancy sensor's user name. Both stop with `FactsError`.

### `hartlib.level_masts`

Every level's masts, one file with a `level` column (owner, 2026-11-21: the level is a column): `PATH`
(`schematic/masts.csv`, written by `tools/schematic/build_masts.py` from the mast and head rows of the device master,
which `build_device_map.py` writes for every level), `FIELDS` (`level`, the mast columns and `PLAN_FIELDS`, the plan
facts the drawing places a mast by: filled for staging's masts, which `device_map_masts.py` places from staging's
block rows, and empty on main and upper, whose
`build_signals.py` places from the plan graph), `read(path, levels=...)` (the rows of `levels`, by keyword, every level when `None`,
each with `level`, `line` and `heads` as system=user pairs), `names(levels=...)`, `visible_names(levels=...)`,
`head_name(user, level)` (a head's internal name from its user name and level: "Head 2L Top" on level 1 ->
IH:HART:C1:2L_Top, "Head 108R Top" on level 2 -> IH:HART:C3:108R_Top, never from a draft physical head),
`head_problem()`, `signal_name()`, `signal_kind()` and `head_count()` (what the drawings show, from the row),
`mast_heads()`, `virtual_level()`, `is_level_head()` and `is_level_mast()`.

`read()` checks the whole file whatever `levels` is and stops with `railroad.FactsError` (a `ValueError`), naming
the file and the line, when the header is not `FIELDS`, a row is shorter or longer than the header, a level is not
1, 2 or 3, a mast name is out of the grammar or given twice (on any level), a dir or leg is not one of its values, a
row has some plan facts and not all, or a row's heads are not system=user pairs of its system name's heads, each its
level's internal name or a wired LCOS head that is the row's planned physical head at its place (its
`device_system_name`'s: staging's masts are bound as built, and a main or upper head is wired only once its device row
swaps it in, so nothing else of theirs reaches MQTT); a virtual mast is in its level's thousand and stands at a buffer
stop.

### `hartlib.operations`

Reads Operations Pro roster files: `cars(path)`, `engines(path)` and `trains(path)` give the `<car>`, `<engine>` and
`<train>` elements of their section (`./cars/car` and so on), in file order; `section(path, name)` is the general
form, `ids(elements)` their ids. `ROSTERS` names the repo's files in `jmri/layouts/hart/operations/` (ADR-015);
the car pipeline passes its own copies in `ops/hart-ops/data/`. A broken file raises `ET.ParseError` naming it.
It only reads: the tools that change a roster keep JMRI's header and layout themselves.

It is also the one reader of the roads and models the rosters and the car pipeline name, kept by hand in
`ops/hart-ops/data/`: `read_roads(path)` gives `Roads` from `roads.csv` (`codes`; `display`, road code to the marks a
card shows; `car_aliases` and `engine_aliases`, a spelling to its road code), and `read_loco_models(path)` gives
`{model: builder}` from `loco_models.csv` in file order. A bad row stops with `RoadsError` (a `ValueError`) naming
the file and line. `engine_lookup.py` and `process_car_images.py` read them; `locos.csv`'s `road_name` refers to
`roads.csv` (its sidecar).

### `hartlib.parked`

The features parked out of the active tables (`PARKED`: Entry/Exit, the Dispatcher System, the USS CTC machine;
`jmri/layouts/hart/parked/README.md`). `split(root)` moves their elements out of a tables root (`build_layout_le.build`
leaves them out of the tables it builds), `freeze(commit)` wrote the parked file `PARKED_XML` once from the live
tables at a commit it records, `check(root, doc)` holds a tables file and the parked file to the rules, `parked_in(root)` names the parked features a tables file leaves out, and `restore`,
`with_parked(features)` and `with_parked_file(features)` give the tables with a feature put back, for the checks of
its data. `shipped_dirs()` and `shipped_jython()` list what the deploy leaves out; `python3 -m hartlib.parked
features|dirs|jython|check|freeze` prints them, runs the check or writes the snapshot.

### `hartlib.coordinator`

`jmri/scripts/signal_coordinator.py` loads its sibling modules (`SIBLING_MODULES`, in load order) from the jython
folder it runs in. `sibling_modules()` reads that tuple from the script's source (it is Jython, so it is not imported)
and stops with `CoordinatorError` (a `ValueError`) when the tuple is missing, given twice, not literal, empty, holds a
name that is not a module name or a module with no `.py` beside the script. `files()` is the script then each module,
and `source()` their text joined in that order, for the checks that read the code as text
(`check_mqtt_no_static_lists.py`, `le_names.lcos_rule`) and the test
that every deploy list ships each module (`tools/hosts/tests/test_coordinator_shipping.py`).
`jmri/layouts/hart/scripts/panel_status.py` lists its parts the same way in `PARTS` (each imported as a module
through the shared loader `jmri/scripts/jython_siblings.py`): `sibling_modules(PANEL_STATUS)`, or `panel_status_parts()`, reads that tuple, and
`files(PANEL_STATUS)` and `source(PANEL_STATUS)` work as for the coordinator. `TUPLE_NAMES` maps each script to its
tuple; any other script is a `CoordinatorError`.

### `hartlib.map_revision`

The station maps carry the system schematic's revision and date (the title block in `page_prefs()`). `fields(prefs)`
reads them, `planned(www, prefs)` gives the text each file it owns should have (`www/data/crew.json`,
`www/data/publications.json`, each current `www/crew/maps/<id>/index.html`), `drift()` names the files that differ
and `apply()` writes them. It writes `crew.json` whole through `crew_master.build()` in `ops/hart-ops/publications/`,
the file's one writer, which `build_crew_json.py` calls too; `crew_master` imports nothing from hartlib, so there is no
cycle. When the crew master does not build (a schema problem, a missing master or `industries.csv`), it only sets the
revision and date in the existing `crew.json` and prints a one-line warning naming the file; the crew-json job of
`check.sh` fails until the master is fixed. `tools/schematic/publish_draft.py` applies it after a publish and checks
it in `--check`.

## The tables.xml traps the lookups exist for

- Several `<sensors>` and `<turnouts>` sections (MQTT, internal, LCC). `root.find("turnouts")`
  returns only the first.
- Every `<block>` appears twice: names only, then the full one with `length`, sensor and
  paths. Put comments and lengths on the full one.
- `root.iter("signalmast")` misses `<virtualsignalmast>`.
- Two Layout Editor panels: `HART Railroad` and `Dispatcher System`.
- Comments are kept, so `for child in el` and `el.iter()` with no tag can yield comment
  nodes whose `tag` is not a string. Use `tables.elements(el)` or `el.iter("tag")`.
- Plain `ET.parse` + `tree.write(path, encoding="UTF-8", xml_declaration=True)` matches
  `save` on the repo file today, but on a fresh Store it drops the stylesheet line and the
  "Written by JMRI" comment and changes the declaration's quotes. A script moved onto
  hartlib keeps them.
- Scripts that edit tables.xml as text with regexes (`check_bean_comments.py`) keep untouched bytes by design.
  Move them only if the regex work is replaced by element edits and the output is the same.

### `hartlib.names`

The device master keeps a turnout's DCC address in its own `dcc` column; JMRI's comment carries it
as the second group (`Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2`). `jmri_comment(wiring, dcc)`
builds one (`devices.comment_of(row)` gives a row's), and `split_dcc(comment)` takes the group out
of a built comment, for the old-form device-map rows and for checks that hold tables.xml to the
master. Read the address from the column; never regex it out of a comment.

### `hartlib.cats`

CATS desk conventions both desk builders use: `station_plate(block)` (`OS Switch 39` -> `39`,
`Track West Ext` -> `West`) and `mast_templates()` (mast user name -> CATS signal template, from
`signal_head_plan.csv`).

### `hartlib.hosts`

The broker and JMRI JSON settings:
`mqtt_broker()`, `mqtt_port()`, `jmri_json_url()`, `read_env_file()`, `env_file_path()`,
`PI_HOST`. The lookup order is in the module docstring.

## Old paths

`jmri/layout_paths.py`, `tools/ops/lib/hart_hosts.py` and `tools/ops/lib/hart_paths.py` are gone; import hartlib.

## Moving a script onto hartlib

1. Not a Jython/JMRI script (see the top). Not owned by another open task.
2. Capture its output first on the current tables.xml: stdout, exit code, and for a writer
   the bytes of what it writes (run writers only on a copy under the temp directory).
3. Replace its `sys.path` lines and its own `ROOT / "jmri/layouts/hart/..."` paths with the
   bootstrap lines above and `hartlib.paths`. Replace its `ET.parse` / `tree.write` with
   `tables.load` / `doc.save()` (or `tables.read` for a reader), and its hand-rolled bean
   loops with the lookups, checking that each lookup returns the same elements (for example
   `root.iter("sensor")` also finds `<sensor>` children outside the sensor tables).
4. Keep its functions' signatures when tests or other scripts call them.
5. Compare against step 2: identical output and exit code; a writer still writes nothing on
   current tables.xml when it should change nothing.
6. Run its tests and `./tools/check.sh`.
7. Give a writer a `--check`, `--dry-run` or `--apply` flag as before.
