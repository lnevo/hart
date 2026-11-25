# One declared build graph: design

A manifest of the pipeline's steps, from which the check.sh check list, the make panels step list and the map's script nodes and edges are generated. This design was written read-only against main at 89b6c792 (2026-11-25). Line numbers refer to that commit.

## 0. Short answer

Do part of it. One manifest for the read-only checks and (later) the make panels steps, with the map's script nodes and edges generated from it, is worth it: it removes four to six hand copies of each step list and replaces the regex scan of shell files. Two parts are not worth it:

- Making declarations the skip mechanism instead of the trace.
- Moving the unit-test jobs or the hand-kept data, host and human nodes into the manifest.

Details are in section 6.

## 1. Today's descriptions, and where they duplicate or disagree

### 1.1 The copies

| What is described | Where (file:line) | Kept honest by |
|---|---|---|
| The 35 read-only checks (name, command) | `tools/check.sh:339-391` (`run` lines in `static_checks`) | nothing structural; scripts are found by regex in `pipeline_map_coverage.py` |
| 10 of those again, for the docs-only path | `tools/ci/docs_checks.sh:18-34` | `test_check_docs_only.py` (`test_each_docs_check_is_also_in_the_full_run`, `test_ci_and_check_sh_run_the_same_docs_checks_script`) |
| What each job reads when the trace can't see (fallback) | `tools/audit/check_stamps.py:79-148` (`BY_KIND` 15 kinds, `EXTRA` 37 entries, `LISTED_ONLY`, `RUNS_JOBS`), `REFS_OF` at `:374` | `test_check_stamps.py` DeclarationTest (audit of what jobs really opened) |
| The 18 panels steps (name, command, step/guard, order) | `tools/schematic/build_panels.sh:207-224` | `test_build_panels.py:24-42` (a fourth copy of the list) |
| The same steps in prose, in order | `build_panels.sh:7-54` (header), `wiki/pipelines/schematic-panels.md:105-122` (table) | `test_build_panels.py` `test_the_header_comment_lists...`, `test_the_wiki_table_lists...` |
| Panels step outputs, publish flag, untraceable programs | `tools/schematic/panel_stamps.py:90-110` (`STEPS`), code globs `:69` | `test_panel_stamps.py` (40 tests) |
| Ordering rules between panels steps | `test_build_panels.py:71-93`, asserted by hand per pair | the same test |
| Every script, its inputs and outputs, and the check relation | `docs/pipeline-map/pipeline_map.json` (424 nodes, 849 edges) | `pipeline_map_coverage.py` (regex over `ENTRY_FILES` at `:49`, `ALLOWED` at `:63`), `build_pipeline_map.py --check`, `test_pipeline_map.py` (64 tests) |
| What counts as stamp machinery for CI | `tools/ci/stamp_gate.py:41` (`MACHINERY`) | `test_stamp_gate.py` |

A new check script today touches at least five places:

1. `check.sh`
2. A map node and its edges, including a `check` edge to `tools/check.sh`
3. A `check_stamps.py` declaration, if it is not plain Python
4. `docs_checks.sh`, if it reads Markdown
5. For a panels step: `build_panels.sh`, the header comment, the wiki table, `test_build_panels.STEPS`, `panel_stamps.STEPS` and the map

### 1.2 Disagreements found

These were measured, not guessed:

- **The masts step's outputs.** `panel_stamps.py:99` declares `masts` writes `devices_generated.csv`, and so do `build_panels.sh:28` ("like device-map and masts it writes the device master") and the comment at `test_build_panels.py:84`. Since naming-layers step 12, `build_masts.py` only reads the device master: its docstring at `:12-14` says so, and `hartlib.devices.WRITERS` (`devices.py:81`) is `("build_device_map.py", "panel_items.json")`. The map has it right (a read edge). The extra output only widens the stamp key, so nothing breaks, but three copies are stale.
- **The check relation in the map.** The map has 28 edges touching `tools/check.sh`. Of the 35 `run` checks, 13 have no edge to `tools/check.sh` at all: `tables-browser`, `repo-guide`, `jmri-additions`, `layout-index`, `layout-docs`, `layout-index-cats`, `panel-contracts`, `digicon-disabled`, `parked`, `wiring-frozen`, `railroad-facts`, `devices` and `desks`. Another 11 have an edge labelled only "check", with no job name. Coverage passes anyway, because it only asks that the script be a node or in ALLOWED, not that the edge exist. Labels are inconsistent: "check check", "check docs-index", "docs-index --check".
- **Panels guards have no map edges.** None of the five guards (`sml-current`, `signals-sync`, `device-master`, `approved-desks`, `approved-live`) has an out-edge. Their inputs show only as edges into the scripts, where they exist.
- **Loose edge kinds.** Edges from a generator to code or a host script carry no `side`, so they read as content edges. Examples: `publish_draft.py -> hartlib/map_revision.py` "revision/date", `panel_items.py -> build_layout_le.py` "placed items", `build_tables.py -> run_sml_discover.sh` "--discovery-base".
- **Scripts the map does not draw.** `check_wiring_frozen.py` is run by check.sh but is in coverage's ALLOWED instead of the map (`pipeline_map_coverage.py:72`). `hartlib.railroad` and two other `-m` checks are covered by the folder node, not as checks.

### 1.3 Churn (last 14 days, no merges)

| File | Commits |
|---|---|
| `tools/check.sh` | 91 |
| `docs/pipeline-map/pipeline_map.json` | 61 |
| `build_panels.sh` | 44 |
| `check_stamps.py` | 22 |
| `panel_stamps.py` | 21 |
| `build_pipeline_map.py` | 70 |
| `test_check_stamps.py` | 16 |

59 of the 91 check.sh commits touch a `run`, `unit` or `later` line. From the subjects, roughly a third add or move a check (registration). The rest are scheduling and perf (job splitting, slow-first, BY_CLASS), the stamp and CI machinery, and the docs-only path. A manifest removes the first kind only, so check.sh churn will not drop to near zero.

## 2. Measurements

### 2.1 Map nodes and edges

424 nodes by kind:

| Kind | Nodes |
|---|---|
| generator | 175 |
| structured | 76 |
| output | 74 |
| unstructured | 71 |
| external | 13 |
| host | 8 |
| human | 7 |

The agent-doc lane is already generated (29 nodes, 55 edges, marked `"gen": "agent-docs"`; precedent at `build_pipeline_map.py:14,127`). The coverage scan finds 119 scripts named by the entry files: 96 are map nodes and 23 are in ALLOWED. Edge sides: 709 content, 96 check, 31 pointer, 7 pull, 3 capture, 2 mirror, 1 history.

| Manifest scope | Script nodes derivable | Edges derivable (of 849) |
|---|---|---|
| A. check.sh read-only checks + public-text, ruff, portal + panels steps (53 scripts) | 51 | 296 (210 content, 86 check), 35% |
| B. every generator an entry file runs | 90 | 454, 53% |
| C. every generator, including hand-run ones declared with `runner = "manual"` | 175 | 659, 78% |

What must stay hand-written whatever the scope:

- **221 file nodes** (structured, unstructured, output). Output nodes could take their description from the step, but data and source files need a human description.
- **28 external, host and human nodes.**
- **190 edges that touch no generator:** 157 content edges such as `human:owner-csv-edits -> switches.csv` or files to hosts, 31 pointers and 2 mirrors.
- **Domains, presets and node order.** The page layout breaks cycles in node order.

### 2.2 check.sh jobs

check.sh has 46 lines that queue jobs (`run`, `later`, `unit`). Locally they expand to about 180 jobs, because unit tests run one job per file and some files one per class or method. CI runs fewer.

The 35 read-only checks run as **one** job, `static`:

- Its fallback declaration is `EVERYTHING` (`check_stamps.py:80`), because it runs bash for panels.
- Its key holds HEAD and the merge base (`REFS_OF`, `:375`).
- Effect: all 35 checks rerun after every commit, and on every CI pull-request run (docs/pipeline-map/checks-and-remote.md, "CI skips what main covered").
- 34 of the 35 are a single Python process, so they trace cleanly. One (`panels`) is bash and has its own step stamps.

The other non-unit jobs:

- `public-text`: Python, declared EVERYTHING.
- `ruff`: not Python, so it uses its declaration only (`:84`).
- `portal`: Python, declared CODE+SITE.

Unit jobs: about 233 test files in 11 folders. By a rough grep, about 72 spawn bash, node or a writing git (hosts 25 of 29, audit 24 of 54, schematic 8 of 33, www 7 of 28) and so fall back to the folder declarations in `BY_KIND` and `EXTRA`. These are test files, not pipeline steps: a manifest of build steps says nothing about what a test file reads. They are left out of the manifest (section 6).

## 3. The manifest

### 3.1 Format and place

- **Place.** TOML under `tools/pipeline/`, one file per runner or lane to keep merges apart: `checks.toml` and `panels.toml`. A later `files.toml` is optional. A loader, `tools/pipeline/manifest.py`, validates the files and prints the lists the runners need.
- **Why TOML.** `tomllib` is stdlib from Python 3.11. The Mac and CI run 3.13. TOML allows the comments this repo depends on to explain each declaration, which JSON does not. `[[step]]` blocks merge line by line, so it needs no custom merge driver like `merge_pipeline_map.py` (384 lines).
- **Fallback.** If WSL on the Windows box is older than 3.11 (check with `make remote CMD="python3 --version"` in stage 0), use a Python module of literal tables instead. The repo already keeps `panel_stamps.STEPS`, `BY_KIND` and `ENTRY_FILES` that way.
- **Ruled out:** PyYAML (a new dependency), and CSV (nested lists).

Fields of a `[[step]]`:

| Field | Meaning |
|---|---|
| `name` | job or step name as printed today (stamps key on it) |
| `runner` | `check` (a check.sh job), `panels` (a make panels step), `manual` (in the map only; run by hand or by a deploy) |
| `cmd` | argv as a list; `{python}` for `$HOPS_PY`; `env` for `PYTHONPATH=...` forms |
| `script` | the map node this step is drawn as (defaults to the first `.py`/`.sh` in `cmd`) |
| `mode` | panels: `step` (writes; stamped) or `guard` (checks only; always runs). check: always `check` |
| `check_args` | what a panels step adds for `--check` (today `--check`; plan-lengths already passes it) |
| `inputs` | data files and globs the step reads, drawn as edges; each item a path or `{path, label}` |
| `quiet_inputs` | read but not drawn (the tables file read through hartlib by 20 scripts); for the trace audit only |
| `outputs` | files and globs it writes (panels: today's `Step.outputs`) |
| `updates` | outputs it also reads and rewrites in part (`plan_generated.json`); exempt from writer-before-reader |
| `programs` | untraceable programs and the files they read (today `Step.programs`, `BY_KIND["ruff"]`) |
| `git` | git refs in the key (`head`, `base`, `origin`): today's `REFS_OF` |
| `publishes` | panels: reads main's published files through git |
| `docs_only` | also in the docs-only path (`docs_checks.sh`) |
| `domain`, `desc` | the map node's lane and text |

The loader checks:

- Names are unique.
- Each `cmd` script exists, or is a `-m` module under its `PYTHONPATH`.
- Each input and output glob matches a tracked file, or is a map node marked `local`.
- `domain` is one of the map's domains.
- Panels writers come before readers in file order, except `updates`.
- No two steps write one file unless both list it in `updates`.

Panels order stays the file order. It is checked, not computed: a topological sort would reorder ties and move steps for no reason.

### 3.2 Example: a check.sh job

The data reads below are today's map edges into `build_wiring_json.py`; the output edges are today's out-edges.

```toml
[[step]]
name = "wiring-json"
runner = "check"
cmd = ["python3", "www/scripts/build_wiring_json.py", "--check"]
domain = "website"
desc = "Builds the website wiring viewer JSON from v86 inventory and the v85 signal splits; check.sh fails while stale."
inputs = [
  { path = "docs/wiring/LCOS_Layout_Inventory_v86.xlsx", label = "LCOS xlsx" },
  { path = "docs/wiring/history", label = "v85 split pins" },
]
outputs = ["www/data/wiring-inventory.json", "www/data/signal-splits.json"]
```

The non-Python case (today `check_stamps.py:84`):

```toml
[[step]]
name = "ruff"
runner = "check"
cmd = ["python3", "tools/audit/check_ruff.py"]
domain = "agents"
desc = "Pyflakes (ruff F rules) over every .py file at the requirements.txt pin."
programs = { ruff = ["**/*.py", "ruff.toml", "requirements.txt", ".gitignore", "**/.gitignore"] }
```

### 3.3 Example: a panels step

Blocked by ADR-033. The values are those of today's `panel_stamps.STEPS["masts"]` with the stale output fixed, and the map's current edges.

```toml
[[step]]
name = "masts"
runner = "panels"
mode = "step"
cmd = ["python3", "tools/schematic/build_masts.py"]
check_args = ["--check"]
domain = "layout"
desc = "masts.csv for every level from the device master's mast and head rows (build_device_map.py writes them)."
inputs = [
  "jmri/layouts/hart/data/devices_generated.csv",
  { path = "jmri/layouts/hart/data/devices_field.csv", label = "staging masts' owner cells by id" },
  { path = "jmri/layouts/hart/data/wiring.csv", label = "reads heads" },
  "jmri/layouts/hart/data/block_lengths.csv",
  "jmri/layouts/hart/data/schematic/interlockings.csv",
  { path = "jmri/layouts/hart/data/schematic/block_overrides.csv", label = "via hartlib.hand_lists" },
  { path = "jmri/layouts/hart/data/schematic/retired_virtual_masts.csv", label = "via hartlib.hand_lists (mast_plan)" },
]
outputs = ["jmri/layouts/hart/data/schematic/masts.csv"]
```

### 3.4 Example: a data-file node

Optional stage 7. Until then this node stays hand-kept in `pipeline_map.json` exactly as now, and steps refer to it by path.

```toml
[[file]]
path = "jmri/layouts/hart/data/switches.csv"
kind = "structured"
domain = "layout"
desc = "Every level's switches, one row per OS block or switch half: legs, hand (plan or owner), local area; staging's Layout Editor turnout, CATS inversion, USS lever."
edited_by = ["human:owner-csv-edits"]
```

Its readers and its writer (`build_hands.py`) are not listed here: they come from the steps' `inputs` and `outputs`.

## 4. What is generated, and what shrinks or goes

### 4.1 Generated from the manifest

- **check.sh's read-only check list.** check.sh asks `python3 tools/pipeline/manifest.py jobs check` for shell-quoted lines and queues them. check.sh already `eval`s `printf %q` lines (`later`/`start_jobs`).
- **docs_checks.sh's list,** from `docs_only = true`.
- **build_panels.sh's step list,** from `manifest.py jobs panels`, and `panel_stamps.STEPS`, read from the manifest (stage 5).
- **The map lane `"gen": "manifest"`.** `build_pipeline_map.py regenerate()` calls a new lane builder beside `AGENT_DOCS.regenerate`. It writes one generator node per step script, plus edges:
  - `input -> script` with its label
  - `script -> output`
  - `script -> tools/check.sh` (side `check`, label `check <name>`)
  - `script -> tools/schematic/build_panels.sh` (side `check`, for guards)

  `--check` fails when the committed JSON differs, and a hand edit to a `gen` entry is rejected, as for agent-docs.
- **The wiki step table** in `schematic-panels.md`: checked against `name`, `cmd` and the first sentence of `desc`, or generated between markers (stage 5).

### 4.2 What happens to `pipeline_map.json`

It **stays committed**, as a mix of hand-kept entries and generated lanes:

- `pipeline_query.py`, `move_path.py`, `wiki/home.md` and AGENTS.md read it with no build step.
- Its hand-kept part (249 nodes and 190 edges in 2.1) has no other home unless stage 7 runs.
- The merge driver already merges `gen` entries by key, and `--check` catches a stale lane.

ADR-036 may take `index.html` and `www/library/pipeline-map.html` out of git. That does not change the JSON; the `pipeline-map-site` check then moves wherever ADR-036 puts the page build.

### 4.3 Checks and code that shrink or go

| Item | Today | After | Stage |
|---|---|---|---|
| `check.sh` `run` lines and their comments | about 60 lines at 339-391 | a loop of about 8 lines | 2 |
| `docs_checks.sh` list | 10 commands | read from the manifest | 2 |
| `test_check_docs_only` sync tests | 2 tests | one loader test | 2 |
| `pipeline_map_coverage.py` | regex scan of check.sh and build_panels.sh as `ENTRY_FILES` | those two entries dropped; manifest steps are nodes by construction; the Makefile and deploy scripts are still scanned, so the tool and most of its tests stay | 3, 5 |
| `ALLOWED` in coverage | 23 | `check_wiring_frozen.py` becomes a manifest step; the plumbing entries stay | 3 |
| map edges for checked scripts | hand-kept, 13 checks with no edge, 11 unnamed | generated and complete | 3 |
| `BY_KIND["static"] = EVERYTHING`, `REFS_OF["static"]` | one wide stamp, reruns every commit | per-check jobs, each traced, `git` only where declared | 4 |
| `build_panels.sh` header (48 lines) and 18 step lines | hand-kept | a pointer to `panels.toml` plus the runner | 5 |
| `test_build_panels.StepList` | 4 copy-sync tests plus hand order rules | one generic writer-before-reader check in the loader tests; DryRun and SmlDiscovery tests stay | 5 |
| `panel_stamps.STEPS` | hand-kept dict | read from the manifest (the script cannot import hartlib: the loader is stdlib only) | 5 |

### 4.4 What does not shrink

- **check_agent_docs.py.** It checks paths named in agent docs and wiki table cell length, not the pipeline.
- **traced.py.** The trace stays the skip mechanism.
- **check_stamps.py's unit-test declarations** (`BY_KIND` unit kinds, `EXTRA`, `LISTED_ONLY`, `RUNS_JOBS`), and with them the audit in `test_check_stamps`.
- **The scheduling half of check.sh.** That covers parallel jobs, slow-first, BY_CLASS and BY_METHOD, the docs-only path, and the CI record and skip modes: most of its 501 lines.

Today's failure ("map coverage, then the stamps audit") would be half solved:

- A new check script gets its map node from its manifest entry.
- A new test that reads a new folder still needs an `EXTRA` line.

### 4.5 The trace as a test of the declarations

This is added; the trace is not replaced.

- After a traced pass, the record step also compares the job's data reads with the step's `inputs`, `quiet_inputs`, `outputs` and `programs`. The reads are the read set minus code globs (`panel_stamps.CODE`, `tools/**`), `.cache` and the plugin.
- An undeclared read is printed in the job's stamp log ("read X, not declared in tools/pipeline/checks.toml").
- It becomes a failure in the weekly full run and in `CHECK_AUDIT` runs once the manifest is clean.
- This keeps the map's edges true without making them carry skip safety.

## 5. Migration

Every stage merges on its own and leaves `check.sh`, `make panels CHECK=1` and CI green. Agent types are from AGENTS.md "Subagents". Tool code outside `tools/schematic` and `tools/hartlib` has no named agent, so it goes to `general-purpose` with `model: "opus"`, in a worktree, with heavy checks through `make remote`.

| # | Stage | Files | Rough size | Agent | Review | Blocked |
|---|---|---|---|---|---|---|
| 0 | Confirm WSL Python is at least 3.11 (else the Python-literal format). Decide ADR-037 "one step manifest" in the wiki. | `wiki/decisions/ADR-037-*.md`, `wiki/decisions/README.md` | docs only | main session | `voice-reviewer` | no |
| 1 | Manifest and loader with **no consumer yet**: the 35 checks plus `public-text`, `ruff`, `portal` in `checks.toml`, inputs and outputs filled from today's map edges by a one-shot script; `manifest.py` (load, validate, `jobs`, `list`); a temporary test that check.sh's `run` lines equal the manifest's; map node for `manifest.py` | `tools/pipeline/checks.toml` (new, about 450 lines), `tools/pipeline/manifest.py` (new, about 250), `tools/audit/tests/test_pipeline_manifest.py` (new, about 200), `docs/pipeline-map/pipeline_map.json` | about 900 added | general-purpose (opus) | medium | no |
| 2 | check.sh and docs_checks.sh read the manifest; the sync test from 1 is dropped. A manifest that fails to load fails the run; a run with zero checks is a failure. Job names unchanged, so stamps stay valid. `stamp_gate.MACHINERY` gains `tools/pipeline/manifest.py`; the job key gains the job's own manifest entry digest (`check_stamps.ALWAYS` / `key()`). | `tools/check.sh`, `tools/ci/docs_checks.sh`, `tools/audit/check_stamps.py`, `tools/ci/stamp_gate.py`, `tools/audit/tests/test_check_docs_only.py`, `docs/pipeline-map/checks-and-remote.md` | about -90 / +80 | general-purpose (opus) | high (CI skip logic) | no |
| 3 | Generated map lane: a `manifest` lane builder beside `agent_docs_map`; a one-shot conversion marks the 51 existing script nodes and their 296 edges `gen: "manifest"`; the 13 missing check edges appear and the 11 unnamed ones get the job name; coverage drops check.sh from `ENTRY_FILES` and `check_wiring_frozen.py` from ALLOWED. | `tools/ops/build_pipeline_map.py`, `tools/pipeline/map_lane.py` (new, about 150), `tools/ops/pipeline_map_coverage.py`, `docs/pipeline-map/pipeline_map.json` (large, mechanical), `tools/audit/tests/test_pipeline_map*.py` | about +300 code, big JSON diff | general-purpose (opus) | medium | no (the PR converting the JSON should land when few map PRs are open; `make orient`) |
| 4a | Trace audit of declarations: warn only (4.5). | `tools/audit/check_stamps.py`, `tools/pipeline/manifest.py`, `tools/audit/tests/test_check_stamps.py` | about +150 | general-purpose (opus) | high | no |
| 4b | Split `static` into one check.sh job per manifest check; `panels` stays one bash job for now. Every check starts with `git = ["head","base"]` (no behaviour change), then each check whose trace replays its git reads drops it, one PR per handful, with the reason. Old `static` stamps are dropped once. | `tools/check.sh`, `tools/audit/check_stamps.py`, `tools/pipeline/checks.toml`, `tools/audit/tests/test_check_stamps.py` | about +60 / -40 | general-purpose (opus) | high | no |
| 4c | Turn the audit to a failure in `CHECK_AUDIT` and the weekly full run, after one clean weekly run. | `tools/audit/check_stamps.py`, `.github/workflows/check.yml` (weekly job) | small | general-purpose (opus) | medium | no |
| 5 | Panels from the manifest: `panels.toml` (18 steps, the masts output fixed); `build_panels.sh` reads it (the SML discovery and runner logic stay in bash); `panel_stamps.STEPS` read from it; `test_build_panels.StepList` replaced by the loader's order check; the wiki table checked against it; coverage drops `build_panels.sh` from `ENTRY_FILES`; the map lane covers the panels scripts and guards. | `tools/pipeline/panels.toml` (new), `tools/schematic/build_panels.sh`, `tools/schematic/panel_stamps.py`, `tools/schematic/tests/test_build_panels.py`, `tools/schematic/tests/test_panel_stamps.py`, `wiki/pipelines/schematic-panels.md`, `tools/ops/pipeline_map_coverage.py` | about -150 / +200 | `schematic-builder` | high (`tools/schematic/`) | **yes: ADR-033** |
| 6 | Optional: check.sh runs each panels step's `--check` as its own traced Python job (check mode writes nothing, so order does not matter) instead of one `bash build_panels.sh --check`. Then CI can skip unchanged panels checks. | `tools/check.sh`, `tools/audit/check_stamps.py`, `docs/pipeline-map/checks-and-remote.md` | about +40 | general-purpose (opus) | high | **yes: after 5** |
| 7 | Optional, not recommended now: move the hand-kept file, host and human nodes and side edges into `files.toml`, so the JSON is wholly generated. | `tools/pipeline/files.toml`, `build_pipeline_map.py`, `merge_pipeline_map.py`, the JSON | large | general-purpose (opus) | medium | no |

**ADR-033 gate for stage 5.** The naming-layers hand-off (`wiki/projects/naming-layers-handoff.md`) marks steps 1 to 14 done as of 2026-11-25, but step 11 still waits on `make panelpro-test` and the deploy, and step 12 on the SML discovery and the owner's panel approval. Stage 5 starts only when:

- those are closed;
- the reshaping session has unclaimed the page (`make orient`);
- `make panels CHECK=1 FULL=1` is all current on main.

Until then `panel_stamps.py` and `build_panels.sh` are not touched, including the masts drift fix.

Order and parallel work:

- 1, then 2 and 3 in parallel (different files, except that both touch the JSON's checks; land 3 after 2), then 4a, 4b, 4c.
- 5 when unblocked, then 6.
- 4b and 6 give the speed gains; 2, 3 and 5 give the single source.

## 6. Risks

- **Stamp correctness.**
  - If the job key does not include the job's manifest entry, a changed command keeps an old stamp and the job is skipped wrongly. Today the key includes all of `tools/check.sh` (`check_stamps.py:413`). Stage 2 must put the entry digest and the loader into the key, with a test that editing one entry's `cmd` reruns that job and only that job.
  - In stage 4b, each check's `git` declaration replaces the blanket HEAD key. A check that reads git through a path the trace does not replay would be skipped wrongly; examples are `build_docs_index.py`'s newest-change order and `repo_guide_page.py`'s file lists. That is why 4b starts with HEAD on every check and removes it one check at a time.
- **CI skip logic.** Today any `check.sh` edit forces a full CI run (`MACHINERY`). If `checks.toml` is machinery, every new check forces a full run, as now. If it is not, the per-entry key above must be right. Add `tools/pipeline/manifest.py` to `MACHINERY` either way. Renamed jobs have no main stamp and run, which is safe.
- **A runner that silently runs nothing.** If the loader fails or returns no lines, check.sh could print ALL PASSED with zero checks. Stage 2 must fail on a load error and on an empty list, with tests. The same applies to build_panels.sh in stage 5.
- **Map clutter or loss in the conversion.** Today's edges carry hand labels ("via hartlib.railroad") and some semantic edges with no `side`. The one-shot conversion must keep every label, and a test must show the converted lane equals the hand one before the hand entries are removed. Reads made through hartlib may grow `inputs` beyond what the map draws today; `quiet_inputs` keeps those off the drawing.
- **Node order.** The page breaks cycles in node order. Generated nodes must be placed where the hand ones were (as agent-docs does), or the drawn map widens. ADR-036 may make this moot for the committed pages.
- **Two writers of the JSON.** Agent-docs and manifest lanes both regenerate it. Both run in one `regenerate()`, so `--check` and the merge driver keep working.
- **Python version on WSL.** Covered by stage 0.
- **Merge traffic during the stage 3 conversion.** The JSON diff is large; parallel PRs that add map nodes conflict on it. The merge driver merges by key, but a hand edit to a node that became `gen` conflicts. Land stage 3 in a quiet window and say so in `make orient`.
- **Gain smaller than the effort.** Registration was about a third of check.sh commits; scheduling, perf and stamp-machinery churn stays. The review-fix churn in `check_stamps.py` and `test_check_stamps.py` is mostly about unit-test declarations and stamp mechanics, which this design leaves alone.

## 7. Recommendation: do part

**Do stages 0 to 4c now and stage 5 once ADR-033 is closed.**

- They remove the repeated step lists: check.sh, docs_checks.sh, the map's script nodes and check edges, build_panels.sh, its header, the wiki table, `test_build_panels.STEPS` and `panel_stamps.STEPS`.
- They remove the regex scan of two of the six entry files.
- They fix drift already present: the masts outputs, the 13 missing and 11 unnamed check edges, the guards with no edges.
- Stage 4b also has a direct gain: the 35 checks stop rerunning together after every commit and on every CI pull-request run.
- Rough effort is 6 to 8 agent-days across the stages.

**Stage 6 (per-step panels checks in check.sh)** is worth doing after 5 only if CI time on panels-heavy PRs is still a problem then. Measure it from logs first.

**Don't:**

- **Make declarations the skip mechanism.** The trace already gives exact, file-level skips for Python jobs, and its rules (short trace, changed-while-running, untraced spawns) took many review rounds to get right. Declarations go stale: the masts entry is stale today. Skipping on them would trade a working safety property for a simpler explanation. Keep the trace for skipping, and use it as the test of the declarations (4.5).
- **Put unit-test jobs in the manifest.** They are discovered by file and split by class; their reads are test fixtures, not pipeline data; `BY_KIND` and `EXTRA` already hold the wide fallbacks. A manifest adds a second place to list a test file.
- **Move the hand-kept nodes now (stage 7).** The JSON stays the committed source for files, hosts, humans and pointers. Moving 249 nodes and 190 edges into TOML changes where they are written, not how many are hand-written. Revisit only if ADR-036 changes how the JSON is used.
