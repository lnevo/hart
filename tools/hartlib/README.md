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
| `TABLES_XML` | `jmri/layouts/hart/output/tables.xml` (ADR-008) |
| `PUBLIC_NAME_MAP` | `jmri/layouts/hart/data/public_name_map.csv` |
| `SIGNAL_WIRING` | `docs/wiring/signals/signal_wiring.csv` |
| `CATS_DIR` | `cats/` |
| `JMRI_USER_FILES` | `~/JMRI_UserFiles` (ADR-014) |

Functions: `lcos_bridge()` (the submodule, else a sibling clone), `car_images_final()`
(`HART_CAR_IMAGES_FINAL`, else the repo copy), `rel(path)` (a repo-relative string for
messages). `layout_paths()` is the old `jmri/layout_paths.py`
dict for the AnyRail-era scripts.

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
hard-linked file is rewritten in place. It refuses to write any `tables.xml` outside the temp directory while PanelPro, DecoderPro,
DispatcherPro or CATS is open (`HART_GUARD_JMRI_RUNNING=0/1` overrides, as for the hook).

Lookups (all take the root element unless noted):

| Function | Returns |
|----------|---------|
| `turnouts`, `sensors`, `signal_heads` | every bean across all manager sections |
| `masts(root, tags=MAST_TAGS)` | `<signalmast>` and `<virtualsignalmast>` in file order |
| `blocks(root, full=True)` | the full `<block>` pass (`full=False`: the names-only pass) |
| `layout_blocks` | `<layoutblock>` beans |
| `layout_editor(root, name=None)` | the main Layout Editor panel, or the one named |
| `layout_editors` | every Layout Editor panel |
| `layout_turnouts(panel)` | `<layoutturnout>` (turnouts and crossovers) on a panel |
| `continuing_sense(lt)` | `CLOSED` (2), `THROWN` (4) or `UNKNOWN` (1) |
| `mast_logics`, `mast_logic_sources`, `mast_logic_pairs` | SML elements, source -> element, (source, destination, element) |
| `system_name(el)`, `user_name(el)`, `text(el, child)` | stripped names and child text |
| `by_system_name`, `by_user_name`, `by_any_name` | dicts over any list of beans |
| `section(root, container, tag)`, `elements(el)` | generic: all sections; children without comments |

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

### `hartlib.hosts`

The broker and JMRI JSON settings, moved from `tools/ops/lib/hart_hosts.py`:
`mqtt_broker()`, `mqtt_port()`, `jmri_json_url()`, `read_env_file()`, `env_file_path()`,
`PI_HOST`. The lookup order is in the module docstring.

## Shims at the old paths

`jmri/layout_paths.py` and `tools/ops/lib/hart_hosts.py` re-export from hartlib so their
callers keep working. Remove a shim once nothing imports it (`tools/ops/lib/hart_paths.py`
is already gone).

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
7. The repo hook (`.claude/hooks/main_guard.py`) blocks table writers while PanelPro or
   CATS is open. It finds them by reading their source: `tables.xml` plus a write call, or
   any import of `hartlib.tables` plus a `.save(` call. Keep a writer's `.save(` call
   spelled that way, and give it a `--check`, `--dry-run` or `--apply` flag as before.
   `save` itself also refuses while JMRI is open.
