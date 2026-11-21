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

### `hartlib.film_pace`

`STEP_S` (0.4) and `FINAL_HOLD_S` (2.0), the pace of the four films on `www/behind/panel-evolution.html`; `durations(n)` and `film_length(n)`. Used by `tools/schematic/evolution.py` and `tools/ctc_history/make_*_evolution_video.py`.

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
| `DEVICES` | `jmri/layouts/hart/data/devices.csv`, the device master (`hartlib.devices`) |
| `WIRING` | `jmri/layouts/hart/data/wiring.csv`, the physical wiring source (`hartlib.wiring`) |
| `CATS_DIR` | `cats/` |
| `JMRI_USER_FILES` | `~/JMRI_UserFiles` (ADR-014) |

Functions: `lcos_bridge()` (the submodule, else a sibling clone), `car_images_final()`
(`HART_CAR_IMAGES_FINAL`, else the repo copy), `rel(path)` (a repo-relative string for
messages). `layout_paths()` replaced `jmri/layout_paths.py`; its one live
caller is `jmri/scripts/generate_nx_pairs.py` (parked with NX), and the AnyRail-era scripts that used the rest
are in `archive/jmri-scripts/`.

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
| `generated_panel(panel)` | True when the panel holds the hidden marker label a generated panel carries (`build_layout_le.py --as-live`); two markers raise ValueError |
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
and `w.wiring_text` the wiring text devices.csv and the JMRI comments carry ("Node: 4 Turnout: 0 | OU: 1 Ports: 1,2").
Staging's rows are as wired in JMRI, plus the fascia buttons, relays and calibration relays, which have no JMRI
device (kinds `button`, `relay` and `calibration`, no index); main and upper's are the detectors the owner placed (planned), the rest of those levels being
given out by `build_device_map.py`'s rule.

### `hartlib.railroad`

The railroad's facts in one place: each fact file read once into typed objects, and the rules between the files
checked together. `python3 -m hartlib.railroad check` (in `tools/check.sh`) runs them; `invariants` lists them.

```python
rr = railroad.Railroad()                  # this checkout's files; Railroad(Sources.under(data_dir), upto=...)
rr.switches[9].legs[0].closed             # staging switches (the level 1 rows of switches.csv + devices.csv)
rr.device_map.sensors["BS Switch 101"]    # IS:HART:C3:B:OS101
rr.check()                                # [Problem(invariant, message)]
```

The files come in **layers**, in the order `tools/schematic/build_panels.sh` makes them: `inputs` (hand-kept:
`switches.csv` (every level's switches, ADR-021), staging's rows of `devices.csv`, `interlockings.csv` (every level),
`lcos_nodes.csv`, `plan_overrides.json` (its `main_upper` section), `block_lengths.csv`), `hands` (the main and upper hands of `switches.csv`, which `build_hands.py` writes into its plan rows), `device_map`, `masts` (`schematic/masts.csv`, every level's masts) and `tables`
(`tables.xml`). `Railroad(upto=layer)` raises `LayerError` when asked for a later layer, so a builder never reads a
stale copy of its own output: `build_device_map.py` loads `upto="inputs"`, `build_cats_panel.py` everything.

| Name | What |
|------|------|
| `Railroad.staging_devices` | `StagingDevices`: staging's (level 1) rows of `devices.csv` in the device layers, `rows` (`StagingDevice`: the master's own columns), `by_name` ((layer, user name) -> row), `names(layer)` |
| `Railroad.switch_rows`, `switches` | `[SwitchRow]`: switches.csv as read (`read_switch_rows`, every row held to its level's shape); `{number: Switch}` of its staging rows (`Switch`, `Leg`; `layout_facts.py` re-exports them) |
| `Railroad.interlockings` (every level), `level_control_points` (its main and upper rows), `local_switches`, `lcos_nodes`, `main_upper_switches` | `Interlocking`, `LocalSwitch`, `LcosNode`, `{number: MainUpperSwitch}` |
| `Railroad.plan_overrides` | `PlanOverrides`: `data` (the whole file), `edits`, `relabel`, `helix` |
| `Railroad.block_lengths`, `hands` | `{name: BlockLength}` (`plan_in`, `measured_in`, `source`, `jmri_in`; `plan_cm()` for the drawings and signal rules), `{label: Hand}` |
| `Railroad.device_map` | `DeviceMap`: `rows` (`DeviceRow`), `blocks`, `sensors`, `planned`, `turnouts`, `heads_by_system`, `of(layer)` |
| `Railroad.masts` | `hartlib.level_masts.read()` rows, every level (`read_masts(path, levels)` gives `[Mast]`: line, level, name, blocks) |
| `Railroad.tables` | `TablesNames`: `root`, `turnouts`, `sensors`, `masts` (user -> system), `blocks` |
| `read_*(path)` | each file alone; `FactsError` names the file and line |
| `check_virtual_names(rows)`, `join_main_upper(cps, local)` | the rules `build_device_map.py` builds by |

`KNOWN` in the module lists problems already reported to the owner, each by its exact message: they print and pass,
anything else fails, and a `KNOWN` entry that no longer happens fails.

### `hartlib.devices`

`jmri/layouts/hart/data/devices.csv` is the one device master for all three levels (ADR-029); `devices.columns.csv`
describes every column and a test holds the two to each other both ways. Staging, main and upper are one structure,
a level differs in column values only. Every reader gets its rows from here (R9b-2, 2026-11-20): `load()` (the
master rows) and `device_map_lines` (the old device-map rows of some levels, plus `role`); `comment_of(row)` is a row's
JMRI comment. The two device maps and `public_name_map.csv` are gone (R9e, 2026-11-20), and so are the six `pnm_`
columns that kept the name map's copy (2026-11-21): their facts are in `cp`, `system_name`, `dcc`, `wiring`,
`jmri_comment` and `notes`. Readers test `role`, never a name prefix.

- `assignment` is `field`, `virtual`, `none` or `spare`; `role` says what the device is; `written_by` is empty for a
  hand-kept row, else a script in `devices.WRITERS` (the one list). A writer replaces only its own rows
  (`replace_rows`) and stops, naming the row, on a key someone else holds.
- `load()` reads and checks once per file state; `check_rows` holds the invariants (unique key, written_by and
  assignment in their sets, field rows `system_name == jmri_name`, order, one comment per row, a description on every
  row). Row order is level, layer, hand-kept rows, then each writer's.
- Writers call `outputs_after(writer, old_form_rows)` (or `outputs_after_rows` with master rows) and write the texts it
  gives: the master's text. Nothing is written until every check has passed.
- `python3 -m hartlib.devices check`. Errors are `DevicesError` (a `FactsError`).
- Staging (`FIELD_LEVEL`, level 1) is the field: its builders carry each row's field facts (system and layout-block
  names, node, wiring, comment, notes, `cp`) over from the row it replaces, so `replace_rows` stops a writer that would
  drop the row of a staging field device (`carries_field_facts`: assignment field or spare, not a panel status bean)
  without naming it in `drops`; a rule's virtual mast, head or part, or a status bean, may go. A line block (`LINE_ROLES`) and its sensor list in `cp` the places it joins, `;` between (`build_device_map.line_cp`); any other row has one control point at most, and `check_rows` holds it.
- A device's kind comes from its row, never from its name (hand-off row 8): `row_role(row, where)` is a row's `role`
  and stops with a `DevicesError` naming `where` (file and line) when the row has none; `is_os(row)` says whether a block
  or occupancy row runs through a switch's points (`OS_ROLES`: `os`, `xover_corner`). A reader that holds only a name
  uses `index()`, the master by (layer, user name), built once per file state: `rows(layer, name)` (one per level the
  device is on; a helix block has two), `role(layer, name)` (stops when the rows disagree, naming their lines),
  `is_os(block)`, `names(layer, roles=, levels=)` (a role query leaves out a device not on the layout yet, a
  level-less row with no role), `has(layer, name)`, `is_unplaced(layer, name)` and `where(row)` (the row's
  "devices.csv line N" for a message). No reader falls back to a name prefix; a tables.xml bean with no row is
  named in a warning and left out.
  Still name-based for now: `role_of` and `block_role`, how a writer stamps the role on a row it makes (`master_row`,
  shared with the mast writers), and `level_devices.block_key` and `occupancy_user`, the owner's naming rule for the
  virtual names (2026-11-17).
- `layout_block` (staging block rows) is the block's JMRI layout block (`ILB...`), which JMRI numbered once; the
  main and upper layout blocks are numbered by the Layout Editor build. A wired head's comment is its `wiring`.

### `hartlib.tables_build`

`tables.xml` is an output (ADR-029, R9c): `tools/schematic/build_tables.py` writes it, and `--check` (in
`tools/check.sh` and `make panels`) fails on any difference. This module holds its parts that come from no drawing:

- `read_template()`: `jmri/layouts/hart/data/tables_template.xml`, what PanelPro owns (settings, memories, the clock
  sensor, the "Hide windows on start" LogixNG), in JMRI's format, every section of `SECTIONS` once and in order, with
  the fixed envelope (`PROLOG`, `EPILOG`) and none of what a Store writes each time (`ENVELOPE_DROPS`).
- `base()`: the template with the staging beans of `devices.csv` (`master_beans`), comments from the wiring columns
  (`bean_comment`), each section in JMRI's system-name order (`jmri_order`). `build_layout_le.py` draws on it.
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
`devices.csv` row: reviewed, `Edit`s to write) and DROPPED (the build's: the repo wins, with what to change instead).
`new_template()` writes the chosen template items, `edited_rows()` the merged cells, and `verify()` checks a
rebuild gives exactly what the plan promised. `read_template()` accepts an extra section a split kept (a Route
table, say), never a second copy of a known one. Errors are `SplitError`.

### `hartlib.level_masts`

Every level's masts, one file with a `level` column (owner, 2026-11-21: the level is a column): `PATH`
(`schematic/masts.csv`, written by `tools/schematic/build_masts.py` from the mast and head rows of `devices.csv`),
`FIELDS` (`level`, the mast columns and `PLAN_FIELDS`, the plan facts the drawing places a mast by: filled for the
masts `build_masts.py` places from a block layer of its own, staging today, and empty on main and upper, whose
`build_signals.py` places from the plan graph), `read(levels, path)` (the rows of `levels`, every level when `None`,
each with `level`, `line` and `heads` as system=user pairs), `names(levels)`, `visible_names(levels)`,
`head_name(user, level)` (a head's internal name from its user name and level: "Head 2L Top" on level 1 ->
IH:HART:C1:2L_Top, "Head 108R Top" on level 2 -> IH:HART:C3:108R_Top, never from a draft physical head),
`head_problem()`, `signal_name()`, `signal_kind()` and `head_count()` (what the drawings show, from the row),
`mast_heads()`, `virtual_level()`, `is_level_head()` and `is_level_mast()`.

`read()` checks the whole file whatever `levels` is and stops with `railroad.FactsError` (a `ValueError`), naming
the file and the line, when the header is not `FIELDS`, a row is shorter or longer than the header, a level is not
1, 2 or 3, a mast name is out of the grammar or given twice (on any level), a dir or leg is not one of its values, a
row has some plan facts and not all, or a row's heads are not system=user pairs of its system name's heads, each its
level's internal name or a wired LCOS head; a virtual mast is in its level's thousand and stands at a buffer stop.

### `hartlib.parked`

The features parked out of the active tables (`PARKED`: Entry/Exit, the Dispatcher System, the USS CTC machine;
`jmri/layouts/hart/parked/README.md`). `split(root)` moves their elements out of a tables root (`build_layout_le.py
--as-live` leaves them out of the candidate), `freeze(commit)` wrote the parked file `PARKED_XML` once from the live
tables at a commit it records, `check(root, doc)` holds a tables file and the parked file to the rules, `parked_in(root)` names the parked features a tables file leaves out, and `restore`,
`with_parked(features)` and `with_parked_file(features)` give the tables with a feature put back, for the checks of
its data. `shipped_dirs()` and `shipped_jython()` list what the deploy leaves out; `python3 -m hartlib.parked
features|dirs|jython|check|freeze` prints them, runs the check or writes the snapshot.

### `hartlib.map_revision`

The station maps carry the system schematic's revision and date (the title block in `page_prefs()`). `fields(prefs)`
reads them, `planned(www, prefs)` gives the text each file it owns should have (`www/data/crew.json`,
`www/data/publications.json`, each current `www/crew/maps/<id>/index.html`), `drift()` names the files that differ
and `apply()` writes them. `tools/schematic/publish_draft.py` applies it after a publish and checks it in `--check`;
`www/scripts/map_revision.py` is the command for it.

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
- Scripts that edit tables.xml as text with regexes (`refresh_bean_comments.py`) keep untouched bytes by design.
  Move them only if the regex work is replaced by element edits and the output is the same.

### `hartlib.names`

`devices.csv` keeps a turnout's DCC address in its own `dcc` column; JMRI's comment carries it
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
