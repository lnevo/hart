# Every script in the pipeline: hand-off (2026-11-25)

Status: active

A plan to map every live script, turn reusable one-off scripts into CLIs, archive the rest, bring speed matching up to the repo's standards and remove duplicate checks.

Two read-only studies on 2026-11-25 found 237 tracked scripts that are not nodes of their own in `pipeline_map.json`: 132 sit under a folder node and 105 have no node at all. They also found six places where checks repeat each other. `pipeline_map_coverage.py` requires only the scripts that an entry file (Makefile, deploy, website deploy) names, so the map falls behind without anyone noticing. The owner chose the options below on 2026-11-25.

| # | Question | Owner's choice |
|---|---|---|
| 1 | Data that STS, JMRI, Operations Pro and DecoderPro write on the hosts | By design: each has its own ingest (`tables-pull`, `ops-pull`, `sts-pull`, the roster sync). Optional: one "waiting to ingest" line in `make orient` |
| 2 | What is parked | NX, the Dispatcher System and the USS CTC machine. The occupancy lamps, the Dispatcher stations and the yard throat blocks are parts of the Dispatcher System. Speed matching is active |
| 3 | How fine the map is | A node per file for pipeline steps, files a host loads, Jython, deploy and speed matching. A folder node is enough for a library or a family of generators (`hartlib`, `card_pipeline`, `publications`). The coverage check fails on a script covered by neither |
| 4 | One-off scripts | A CLI when it serves a common operation; otherwise archived |
| 5 | Helix and main-level benchwork generators (24 `make_*.py`) | Archive after the benchwork build |
| 6 | Old speed-matching runs | Must stay reviewable without changes. The 2026-11-08 data stays; the scripts that only made it, and the two STRR vendor scripts, are archived |
| 7 | The `desks` check (`validate_cats_panel.py`) | Removed: the desks are generated, byte-checked and fingerprinted |

## How to run this

- Merges go through the queue held by session `hart-95`: "ready #N", merge only on "go #N" (2026-11-25). Lane A follows every open PR that edits `pipeline_map.json`; `make map` draws the check scripts' boxes from `checks.toml`, so lane A adds by hand only scripts no manifest step runs.

- Lanes A to E each open their own PR from their own worktree. Full checks run only through `make remote`.
- `tools/pipeline/checks.toml`, `tools/check.sh` and `tools/audit/check_stamps.py` belong to the ADR-037 session. Lane E sends its edits to those files through it, as the data-masters lanes do ([`data-masters.md`](data-masters.md)).
- Lane A's large JSON diff lands when `make orient` shows few open map changes (ADR-037 consequence 4), after ADR-037 stage 4c.
- Lanes do not edit files the data-masters lanes own: `tools/wiring/`, `ops/hart-ops/data/`, `bin/cars` and the schematic data.
- Scripts of parked features are mapped with `status: parked` where they are, never fixed or moved (AGENTS.md).
- Lane agents write their status lines to `.claude/progress/pipeline-next-<lane>.md`.

## A. The map covers every script (M to L)

- Extend `tools/ops/pipeline_map_coverage.py`: every tracked `.py` and `.sh` outside `archive/`, `external/`, `reference/` and tests is a node, or sits under a folder node marked as a library or generator family. Anything else fails.
- Add the 105 missing nodes with their read and write edges. These include the deploy stack (`tools/hosts/deploy/*`, `apply_hart_package_local.sh`, `pack_roster_stage.sh`), the PanelPro control scripts, the Layout Editor and CATS desk build modules, the Jython scripts, the `cats/scripts` helpers, `.claude/hooks/*` and `.cursor/hooks/main_guard.py`, and each speed-matching script, plus the Pi unit `hart-speedmatch-live.service` and its data and runtime stores.
- The writers of files a host loads come first: `ship_*.sh`, `stage.sh`, `apply_hart_package_local.sh`, `pack_roster_stage.sh`, `panelpro_profile.py` and `le_tables.py`.
- Map the parked scripts in `jmri/layouts/hart/scripts/` as parked, including `apply_dispatcher_roster_profiles.py`. `refresh_bean_comments.py` is live: it has a live `check` mode.
- `www/data/invites.json`, `www/data/panels.json` and `www/scripts/serve_portal.sh` lose `status: parked`. They are only left out of the public build.
- Agent: `general-purpose`, opus. No code review for the JSON; `/code-review medium` for the coverage check.

## B. One-off scripts become CLIs (M)

**Done** in #1148: `cats_inspect.py`, `films.py` and `cs105.sh` (with `consist query|attach|detach`, refused while the operating flag is set); `seed_default_thrown_turnouts.py` is now `diagnose_turnout_states.py`; `rebuild_station_map_full.py` runs in `rebuild_publications.sh`.

| CLI | Folds | Note |
|---|---|---|
| `cats/scripts/cats_inspect.py {edges,grid,trace}` | `analyze_cats_edges.py`, `dump_cats_grid.py`, `digicon_trace.py` | Read-only inspectors of a CATS panel |
| `tools/ctc_history/films.py {ctc,cats,le}` | the three `make_*_evolution_video.py` | `docs/ctc/history/README.md` steps follow |
| `tools/ops/cs105.sh {reboot,consist,roster-sync}` | `cs105_reboot.sh`, `cs105_roster_sync.sh`, `cs105_consist.py` | `cs105_consist.py` makes live LCC writes: it is refused while the operating flag is set |

Also in this lane:
- Rename `seed_default_thrown_turnouts.py` to what it does: it only diagnoses.
- Add `rebuild_station_map_full.py` to `tools/ops/rebuild_publications.sh`: `rebuild_operator_primer.py` and the website read its PNG.

Agent: `general-purpose`. `/code-review medium`.

## C. Archive (S)

- The 2026-11-08 speed-matching scripts that made that session's files: `runner/step_runner.py`, `runner/move_to.py`, `analyze_profile.py` and `propose_table.py`. Their README and `RERUN_PLAN.md` links point into `archive/`, and the `ruff.toml` exception for the runner goes. `block_speeds.py` and every data file stay.
- `docs/jmri/speedmatching/STRR_*.py` (two third-party scripts), with their `ruff.toml` and size-guard exclusions.
- `tools/benchwork/helix/` and `tools/benchwork/main_level/` generators, once the owner says the benchwork build is finished.
- Kept: `cats/scripts/sync_hart_package.sh` (ADR-007 keeps the old command).
- Use `tools/ops/move_path.py` for every move. Docs only, no review.

## D. Speed matching meets the repo's standards (M)

**Done** in #1149, with the speed-matching part of lane C. `speedmatch.py` (also `make speedmatch`) runs every step. `pom --send` goes through `drop_job.sh`'s gates, and `pom_write.py` holds `/tmp/speedrun.active` while it writes. The 2026-11-08 raw logs are not in the Pi backups (they were in the Pi's `/tmp`), so that session stays as its CSVs.

- One `speedmatch` CLI with subcommands: `job` (`make_job.py`), `drop` (`drop_job.sh`), `pom` (`pom_write.py`), `compare` (`preflight_compare.py`, `stoptest_compare.py`), `to-roster` (`profile_to_roster.py`), `lengths` (`infer_block_lengths.py`) and `rename-ext` (`rename_extension_tracks.py`).
- `pom` replaces the hand procedure in `POM_GUARD.md` (lines 150 to 168), which skips the operating-flag gate and the "runner active" check.
- `stage.sh` ships the 2026-11-08 `speed_by_step.csv` from `docs/`. That becomes a named data file under `jmri/layouts/hart/data/`.
- `tools/hosts/live_paths.txt` lists the whole `dashboard/` folder. The Mac-only `server.py` and `static/` come out of it.
- Host paths come from `tools/env/load_env.sh`: `pom_write.py`, `dashboard/server.py`, `preflight_compare.py` and `pom_guard.py`.
- Split `pom_guard.py` (934 lines) in a commit that changes no behaviour. Add tests for `dashboard/server.py` beyond `Hub`.
- The Jython runners share names through `execfile`, so `ruff.toml` turns F821 off for them. Make the names explicit so a typo fails.
- Old runs: the 2026-11-13 session is in the run viewer (`www/ai/speed-runs.html`). Add the 2026-11-08 session with `export_site_runs.py` if its raw logs are in the Pi backup (`~/speedmatch`, ADR-035); not checked yet.
- Agent: `general-purpose`, opus. `/code-review high`, because the code runs on the Pi.

## E. Remove duplicate checks (S to M each)

CI sample (2,456 runs, 2026-10-31 to 11-25): 138 failed; 93 real faults, 29 stale generated files, 12 flaky or no log, 4 unclassified. 26 of the 39 manifest checks never failed, which alone is no reason to remove one.

| # | Duplicate | Change |
|---|---|---|
| 1 | `.claude/hooks/check_after_edit.py` keeps its own list of 8 checks; `test_guards.py` keeps it matched to the manifest | Mark the steps in `checks.toml`; the hook reads the manifest; the matching test goes |
| 2 | `check_device_master.py` and `railroad-facts` both run `device_row_problems` | **Kept** (checked 2026-11-25): the guard is the only place `make panels` runs it; without it a duplicate DCC address or a block with no occupancy row reaches the CATS desks |
| 3 | Tests that pin the exact text of `check.sh` and the workflow (`test_check_sh_tables.py`, `test_check_docs_only.py`) | A run test for each, or drop it where one exists |
| 4 | The docs-only unit-test list in `docs_checks.sh`, kept by four guard tests | Generated from the stamps declarations |
| 5 | `desks` (`validate_cats_panel.py`) | Removed with its `make desks` call; the desks are generated and byte-checked |
| 6 | `phase02` may repeat `check_layout_facts.py` | **Kept** (checked 2026-11-25): it alone catches an OS block in the master with no `switches.csv` row, a missing secondary OS block, and a repeated block name in a Store candidate |

Checked and needed: the two `tables.xml` checks that look like repeats (they cover Store candidates and the deploy gate), CI's second panels run on a plugin bump, the stamps machinery, and the map checks.

## Open for the owner

- When the benchwork build is finished, so lane C can archive the generators.
- `docs/ap/electrical/build_soq.py` and `make_drawings.py` have no callers: keep as the AP package's tools, or archive.
- ~~The optional "waiting to ingest" line in `make orient`.~~ Done 2026-11-25 (owner's decision that day): a "Waiting to ingest" section, one read-only line per source, each naming its pull command; the live STS line says "not checked" with why.

## Done when

Lanes A to E are merged, the coverage check fails on an unmapped script, `./tools/check.sh` (`FULL=1` through `make remote`) passes on main, and this page is `Status: done`.
