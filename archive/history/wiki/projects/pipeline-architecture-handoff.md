# Pipeline architecture review: hand-off (2026-11-24)

Status: done (2026-11-24)

The 2026-11-24 architecture review of the panel pipeline (`make panels`, `check.sh`, CI, the deploy gate) found no runaway recursion: a second `make panels` on main d6944380 skipped every step. It found one manual loop that costs a round trip on every layout change, steps run outside or out of order, and the same check lists kept in four places. Six items follow, each its own PR, in this order.

| # | Item | Size | Decision |
|---|---|---|---|
| 1 | `check.sh` runs `build_panels.sh --check` in place of its own copy of the panel checks | S | none needed (outputs byte-identical) |
| 2 | `panel_items.py` becomes a `make panels` step; the plan-lengths guard moves after device-map | S | none needed |
| 3 | `make panels` on the Mac runs SML discovery itself when it is stale | M | **owner**, before building |
| 4 | `detail_sheets` moves out of the hand-edited `preferences.json` | S | none needed, if the plugin can read it from a generated file (check first) |
| 5 | The deploy gate trusts CI's pass of the `origin/main` commit it ships | M | **owner**, before building |
| 6 | Profile the cold Layout Editor build | L | none; do it before the next plugin update |

## Outcome (2026-11-24)

| # | PR |
|---|---|
| 1 | #1066: `check.sh` runs `build_panels.sh --check` once; `panel-status` went with it |
| 2 | #1068: `panel-items` step; `plan-lengths` after `device-map` |
| 3 | #1067: owner chose the automatic run on the Mac; stale is exit 4, a lock in /tmp allows one discovery at a time, and a refused discovery restores `tables.xml` |
| 4 | #1069: `preferences_generated.json` |
| 5 | #1070: owner chose to trust CI; `tools/hosts/deploy/ci_pass.py` decides, and any doubt runs G4 |
| 6 | profiled, cuts proposed in [`efficiency-plan.md`](../../../../docs/pipeline-map/efficiency-plan.md) ("Cold Layout Editor build profiled"); they are plugin changes, not built yet |

## How to run this

- Read `tools/schematic/build_panels.sh` (its header lists every step and why it runs where it does) and [`../pipelines/schematic-panels.md`](../../../../wiki/pipelines/schematic-panels.md) first.
- Work in `make wt TOPIC=<topic>` worktrees. Items 1, 2 and 4 are code: `/code-review medium` before merge. Every layout output must come out byte-identical (`make panels CHECK=1` and the approved fingerprints pass with no new approval).
- Items 1, 2 and 4 touch different files and can run as parallel worktree agents (`schematic-builder` for 2 and 4). Item 3 needs the Mac's PanelPro and stays in the main session. Ask the owner items 3 and 5 together, multiple choice, before building either.
- Pipeline map: each PR that adds, moves or removes a step updates `docs/pipeline-map/pipeline_map.json` (`tools/ops/pipeline_map_coverage.py` in `check.sh` fails otherwise).

## 1. One list of panel checks

**Found:** the static job of `tools/check.sh` (lines 241-255) runs 12 of the 16 `build_panels.sh` steps as separate `--check` commands. It does not run `schematic` (`publish_draft.py --check`), `head-plan` (`build_hart_signal_heads.py --check`) or `sml-current` (`check_sml_current.py`). CI's only `build_panels.sh --check` is the cache warm-up in `.github/workflows/check.yml` (about line 180): it runs only when the plugin pin changes, and its verdict is discarded (`|| echo ... check.sh reports them`). So no CI check holds `signal_head_plan.csv`, which ships to the hosts, or the published schematic draft.

**Do:** replace those `check.sh` lines with one `run panels bash tools/schematic/build_panels.sh --check`. The static job already runs its checks one after another, so nothing is lost; the stamps in `build_panels.sh` skip current steps.

**Watch:** `.claude/hooks/check_after_edit.py` keeps a `CHECKS` list that `tools/audit/tests/test_guards.py` (`test_after_edit_checks_match_check_sh`) holds to `check.sh` lines; any hook entry for a removed line has to point at the new job. `tools/audit/tests/test_check_sh_tables.py` pins parts of `check.sh` text. `check.sh` passes `HART_TABLES` to the static checks: confirm `build_panels.sh --check` honours it or says it does not. Time the new job against the old lines' sum (the log prints each).

## 2. Every device-master writer inside `make panels`, in order

**Found:**
- `tools/schematic/panel_items.py` writes device-master rows (the status beans, `written_by` `panel_items.json`), which the `tables` step reads, but `make panels` does not run it. After an edit to `panel_items.json`, `make panels` says "all current" and only `check.sh` (`panel-status`, line 274) fails.
- The `plan-lengths` guard runs before `device-map`, but `plan_lengths.py --check` reads the device master (`devices.index()`, about line 441) to find the OS blocks. When device-map changes the blocks, the guard checks the old ones.

**Do:** add `step panel-items python3 tools/schematic/panel_items.py` before `tables` (after `masts`, the other device-master writer, is the natural place), and move `guard plan-lengths` to just after `step device-map`. Update the step list in the header and the pipeline page. `panel-status` in `check.sh` then goes with item 1.

## 3. SML discovery without the second `make panels` (owner decision)

**Found:** after a structural change, `make panels` stops at the `sml-current` guard; the owner or agent runs `jmri/layouts/hart/scripts/run_sml_discover.sh` (PanelPro on the Mac, about 3 min), then `make panels` again, then the checks and the approval. Discovery itself stays stock (memory: SML discovery is the reference).

**Options to ask:**
- (Recommended) On the Mac, when the guard says stale, `make panels` runs `run_sml_discover.sh` and goes on to `tables`. Off the Mac (CI, Windows, `make remote`) it stops as now. It must still refuse while PanelPro or CATS runs, and on an unapproved panel (`HART_TABLES_REVIEW=1` stays the way to discover on one under review).
- Keep it by hand, but print the one command to run and resume from `tables`.
- Leave as is.

**Check before building:** the panelpro and panel-approval skills (`.claude/skills/`) and what `run_sml_discover.sh` does on failure (it leaves `tables.xml` as the discovery base).

## 4. `detail_sheets` out of `preferences.json`

**Found:** `tools/schematic/build_staging_sets.py` (line 167) writes the `detail_sheets` key into `preferences.json`'s staging section, a file the owner edits by hand. T6b (#901) moved the generated parts of `plan_overrides.json` to `plan_generated.json` for the same reason. Readers: `publish_draft.py` (line 309, the station detail sheets) and `staging_device_map.py`.

**Check first:** `detail_sheets` is a plugin preference read through `hartlib.layer_files.view`. Find whether the view can merge a generated preferences layer; if the plugin only takes it from `preferences.json`, this needs a generated preferences file in `layer_files` (the same pattern as `plan_generated.json`). If that is more than small, record why and close the item.

## 5. The deploy gate and CI's pass (owner decision)

**Found:** since PR #1063 (2026-11-24) a deploy to the Pi or Windows ships only `origin/main` itself, and CI ran `check.sh` on that exact commit. The gate (`tools/hosts/deploy/gate.sh`) still regenerates `tables.xml` to compare it (`build_tables.py --check`, G4), the slowest gate step on a cold cache.

**Options to ask:**
- (Recommended) The gate skips G4's regeneration when CI's check stamps (`tools/audit/check_stamps.py`, "main's last full pass") record a pass for this commit, and runs it as now otherwise. G4b (approvals) and G5 (Digicon) stay; they are fast.
- Leave the gate as is: it is the last check before the hosts, and the cost is only on a cold cache.

## 6. The cold Layout Editor build

**Found** (docs/pipeline-map/efficiency-plan.md, "Full rebuild timed", 2026-11-23): a `make panels FULL=1` with an empty plugin cache took 431 s, 343 s of it in `sml-current`, which builds `tables.xml` in memory, the Layout Editor panel first. Warm runs take 4-6 s. The `tables` step builds the same thing again, from the cache (2 s).

**Do:** profile `build_layout_le.build` cold (`python3 -m cProfile`, `SCHEMATIC_CACHE=` empty), name the passes that take the time (the label placement is the suspect), and propose cuts that keep the panel byte-identical. Do this before the next plugin pin bump, which empties the cache.

## Not in this plan

The guard-layer overlap audit (2026-11-24) is done: two duplicate rules were removed in #1064 and the rest kept. Test noise and the main-only deploy rule are done in #1063.
