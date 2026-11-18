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
| `PUBLIC_NAME_MAP` | `jmri/layouts/hart/data/public_name_map.csv` |
| `SIGNAL_WIRING` | `docs/wiring/signals/signal_wiring.csv` |
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
| `hand_drawn_only(path, script)` | None, or why a one-off edit of the hand-drawn panel must not run on that file's panel |
| `layout_turnouts(panel)` | `<layoutturnout>` (turnouts and crossovers) on a panel |
| `continuing_sense(lt)` | `CLOSED` (2), `THROWN` (4) or `UNKNOWN` (1) |
| `mast_logics`, `mast_logic_sources`, `mast_logic_pairs` | SML elements, source -> element, (source, destination, element) |
| `system_name(el)`, `user_name(el)`, `text(el, child)` | stripped names and child text |
| `by_system_name`, `by_user_name`, `by_any_name` | dicts over any list of beans |
| `section(root, container, tag)`, `elements(el)` | generic: all sections; children without comments |

### `hartlib.railroad`

The railroad's facts in one place: each fact file read once into typed objects, and the rules between the files
checked together. `python3 -m hartlib.railroad check` (in `tools/check.sh`) runs them; `invariants` lists them.

```python
rr = railroad.Railroad()                  # this checkout's files; Railroad(Sources.under(data_dir), upto=...)
rr.switches[9].legs[0].closed             # staging switches (switches.csv + switch_legs.csv + the name map)
rr.device_map.sensors["BS Switch 101"]    # IS:HART:C3:B:OS101
rr.check()                                # [Problem(invariant, message)]
```

The files come in **layers**, in the order `tools/schematic/build_panels.sh` makes them: `inputs` (hand-kept:
`switches.csv`, `switch_legs.csv`, `public_name_map.csv`, `control_points_main_upper.csv`,
`local_switches_main_upper.csv`, `lcos_nodes_main_upper.csv`, `main_upper.plan_overrides.json`, `block_lengths.csv`,
`schematic/staging_masts.csv`), `hands` (`hands.csv`), `device_map`, `masts` (`main_upper_masts.csv`) and `tables`
(`tables.xml`). `Railroad(upto=layer)` raises `LayerError` when asked for a later layer, so a builder never reads a
stale copy of its own output: `build_device_map.py` loads `upto="inputs"`, `build_main_upper_masts.py`
`upto="device_map"`, `build_cats_panel.py` everything.

| Name | What |
|------|------|
| `Railroad.name_map` | `NameMap`: `rows` (`NameRow`), `live` ((layer, name) -> row), `aliases`, `names(layer)` |
| `Railroad.switches` | `{number: Switch}` (`Switch`, `Leg`; `layout_facts.py` re-exports them) |
| `Railroad.level_control_points`, `local_switches`, `lcos_nodes`, `main_upper_switches` | `LevelControlPoint`, `LocalSwitch`, `LcosNode`, `{number: MainUpperSwitch}` |
| `Railroad.plan_overrides` | `PlanOverrides`: `data` (the whole file), `edits`, `relabel`, `helix` |
| `Railroad.block_lengths`, `staging_masts`, `hands` | `{name: BlockLength}`, `[StagingMast]`, `{label: Hand}` |
| `Railroad.device_map` | `DeviceMap`: `rows` (`DeviceRow`), `blocks`, `sensors`, `planned`, `turnouts`, `heads_by_system`, `of(layer)` |
| `Railroad.level_masts` | `hartlib.level_masts.read()` rows |
| `Railroad.tables` | `TablesNames`: `root`, `turnouts`, `sensors`, `masts` (user -> system), `blocks` |
| `read_*(path)` | each file alone; `FactsError` names the file and line |
| `check_virtual_names(rows)`, `join_main_upper(cps, local)` | the rules `build_device_map.py` builds by |

`KNOWN` in the module lists problems already reported to the owner, each by its exact message: they print and pass,
anything else fails, and a `KNOWN` entry that no longer happens fails.

### `hartlib.level_masts`

The main and upper levels' control-point masts: `PATH` (`main_upper_masts.csv`, written by
`tools/schematic/build_main_upper_masts.py`), `read()` (rows with their `heads` as system=user pairs), `names()`,
`head_name()` (the virtual head from its user name: "Head 108R Top" -> IH:HART:C3:108R_Top, never from the draft
physical head), `mast_heads()`, `is_level_head()` and `is_level_mast()`. Used by `build_layout_le.py`,
`audit_panel_contracts.py` and `polish_hart_layout_editor.py`.

### `hartlib.hand_drawn`

The last hand-drawn `tables.xml`, read from git at `COMMIT` (main just before the Layout Editor cut-over): `tables_bytes()`,
`tables_path()` (a read-only temporary copy, one per process) and, for tests, `skip_unless_available()`. Used by
`build_layout_le.py` (`template_tables`) and the tests of the cut-over and of the one-off scripts that only
ever edited the hand-drawn panel. No copy of the old file is kept in the tree.

### `hartlib.parked`

The features parked out of the active tables (`PARKED`: Entry/Exit, the Dispatcher System, the USS CTC machine;
`jmri/layouts/hart/parked/README.md`). `split(root)` moves their elements out of a tables root (`build_layout_le.py
--as-live` leaves them out of the candidate), `freeze(commit)` wrote the parked file `PARKED_XML` once from the live
tables at a commit it records, `check(root, doc)` holds a tables file and the parked file to the rules, `parked_in(root)` names the parked features a tables file leaves out, and `restore`,
`with_parked(features)` and `with_parked_file(features)` give the tables with a feature put back, for the checks of
its data. `shipped_dirs()` and `shipped_jython()` list what the deploy leaves out; `python3 -m hartlib.parked
features|dirs|jython|check|freeze` prints them, runs the check or writes the snapshot.

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
- Scripts that edit tables.xml as text with regexes (`apply_public_names.py`,
  `refresh_bean_comments.py`, `apply_le_sml_facing.py`) keep untouched bytes by design.
  Move them only if the regex work is replaced by element edits and the output is the same.

### `hartlib.names`

`public_name_map.csv` keeps a turnout's DCC address in its own `dcc` column; JMRI's
comment carries it as the second group (`Node: 4 Turnout: 0 | DCC: 100 | OU: 1 Ports: 1,2`).
`row_comment(row)` gives the JMRI comment for a map row, `jmri_comment(comment, dcc)` builds
one, and `split_dcc(comment)` takes the group out of a JMRI or Device-map comment. Read the
address from the column; never regex it out of `comment`.

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
