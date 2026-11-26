# STS helpers cleanup

- **Owner:** lnevo
- **Hand-off:** [`archive/history/wiki/projects/sts-handoff-2026-11-18.md`](sts-handoff-2026-11-18.md) (Pi deploy of the HART-names change, then this plan).
- **Status:** 2026-11-18. Done: the HART-names change is on the Pi after the owner's UAT check (sts-docker b44f2d5 with #19, sts-plugins a2884b4 with #6; #20 on top only changes a browser test). Step 1 merged as sts-helpers #9, step 2 as sts-plugins #7 and sts-helpers #10. Step 4 dropped by the owner: sts-helpers is not moved into sts-docker, nothing new is installed there, and `rewind_session.sh` and `sync_operational_steps.sh` stay as they are (the step 1 guard on `rewind_session.sh` stays; `sync_operational_steps.sh` is unguarded). Follow-ups the same day: sts-docker #21 (stale CLI references, the dead `weigh_failed` check and `warm_start_pending_pickup_ids` removed) and sts-helpers #11 (the sandbox guard also requires the API URL to be the checked container; scripts print the URL of the stack they ran on). Both passed the owner's UAT check and went on the Pi the same day: `pi_sts_update.sh --status` shows sts-docker 7040132 and sts-plugins c06f944, live `/health` is `live`, session 5. Nothing from this plan is left to deploy.
- **Repos:** `external/sts-helpers` (lnevo/sts-docker-helpers, `main`), `external/sts-plugins` (lnevo/sts-plugins, `main`), `external/sts-docker` (lnevo/sts-docker, working line `active`). Each step is a PR in the submodule repo, then one hart PR moves the submodule pointers.

## Review findings (2026-11-18)

Submodules were at their remote heads: sts-helpers a52e7a2, sts-plugins ab8d4cc, sts-docker 424d819.

**Stack guard is wrong.** `lib/sts_api.sh:25-33` and `lib/sts_api.py:42-46` expect `live` unless `COMPOSE_PROJECT_NAME=sts-sandbox`. The Mac stack reports `uat` (`sts-docker/docker-compose.yml:20`) and only the Pi release stack reports `live`. So writes on the Mac are refused without `STS_EXPECT_STACK=uat`, and on the Pi the guard passes for any script, simulations included. The docker-exec scripts (`bin/rewind_session.sh`, every `bin/run_*` sweep) have no guard. GETs never check the stack.

**Warm start.** The live workflow (`hart_session`, Pi copy in `sts-docker-data/pi/backups/session_editor/`) has no warm-start step; session 0 restores `hart_seed0`. `hart_warm_start.php` (1,998 lines) is still reached through `POST /admin/warm-start`, `/admin/sessions/begin`, `/admin/sessions/play`, the track_scale step, the station report and simulator status: about 1,610 lines. Not reached:

- No caller at all (about 212 lines): `hart_count_shenango_pickup_for_ck1` (98), `hart_count_loaded_coke_at_shenango` (112), `hart_count_ck1_on_train` (139), `hart_seed_island_spotting` (1068), `hart_assign_nvl_scully_block` (1165), `hart_ck1_ensure_coke_on_train` (1266). Only sts-docker `docs/plans/` mention them.
- `--ck1-test` only (about 190 lines): `hart_ck1_outbound_cars_detail` (895), `hart_log_ck1_outbound_cars` (938), `hart_begin_ck1_test_session` (1173), the `run_ck1_test` branch in `hart_run` (1378, 1510), defaults at 45 and 52.
- Never set by any caller: the `stop_when_locals_secured` branch in `hart_run` (1428-1451) and the final `else` of `hart_run_session_work` (838-840).
- Stale fallback path in `hart_track_scale_available` (61-66).

Line numbers are from ab8d4cc; check them again before editing.

**What is generic in sts-helpers.** About 12 of 180 files. No hard-coded paths or hosts; HART-ness is job, seed and dump names.

- Generic: `lib/sts_api.{sh,py}`, `lib/sts_paths.py`, `lib/paths.sh` (except the dump-name resolvers at 87-117), `bin/run_catalog_workflow.sh`, `bin/run_catalog_tests.sh` with `validate_catalog_api.php` and `generate_test_workflow_csv.php`, `bin/snapshot_session_db.sh`, `bin/backup_sessions.sh`, `bin/fix_temp_permissions.sh`, `bin/verify_sts_runtime.sh` (broken: lines 23-24 require plugin files sts-docker no longer ships), `diagnostics/_probe_*.php` (5), `tests/test_paths.py`.
- Already in sts-docker, so redundant here: all of `session/` and `switchlists/` (old forks of sts-docker `sts/` files, unreferenced), `sts/*.php` legacy CLIs (replaced by `sts-docker/sts/api/tasks/`), `bin/generate_switchlists.sh` (stub that exits 2), `tools/sanitize_sts_backup_sql.py` (restore handles table-name case).
- Risky: `bin/sync_operational_steps.sh:42-44` overwrites the container's `sts/` tree and deletes `index.php`.
- HART-only, stays: seed tools, 55 migrations, about 35 diagnostics, 13 `run_*` sweeps, `track_scale/`, `backups/`.
- Unreferenced anywhere (about 30): see the step 2 list.
- Done 2026-11-18: sts-docker core no longer names HART (sts-docker #19, sts-plugins #6). Session dump names come from the manifest key `session_backup_prefix` (hart_layout sets `hart_session`, default `session`); railroad name and initials fall back to `Railroad`/`RR` (HART's database sets both); staging jobs come only from the scenario hook or config; `bin/check_plugin_boundary.sh` now catches `hart` and `STG-` and scans the generated catalog; the sts-plugins check is case-insensitive and catches bare HART, 10.0.0.x and /Users/ paths. Not on the Pi yet: needs the owner's UAT check, then `tools/hosts/pi_sts_update.sh`.

## Plan

Steps 1 and 2 touch different files and can run in parallel. Step 3 is folded into step 2. Step 4 waits for step 1 to merge.

Every brief carries the code-quality checklist (clear errors, no silent fallbacks, invariant checks, input validation, no duplication). Agents that edit files run with `isolation: "worktree"`. Agents test only in a sandbox stack (8981); none writes to the Mac UAT (8980) or the Pi. After the PRs, the owner approves on the Mac UAT copy before `tools/hosts/pi_sts_update.sh` puts it on the Pi (ADR-020).

| Step | Who | Model / effort | Why |
|------|-----|----------------|-----|
| 1 Stack guard | main session | Opus, medium | Safety logic for live writes; small |
| 2 Dead code + `--ck1-test` | `general-purpose` agent, worktree | Sonnet, low | Deletion from an exact list |
| 4a Design the move | main session | Opus, medium | Interface choices for sts-docker |
| 4b Do the move | `general-purpose` agent, worktree | Sonnet, medium | Mechanical once designed |
| Review | `/code-review medium` per code PR | main session | AGENTS.md close-out rule |

### Step 1: fix the stack guard (main session)

In sts-helpers:

1. `sts_api_expected_stack` / `expected_stack()`: default `uat` instead of `live`. `STS_EXPECT_STACK` still overrides; `COMPOSE_PROJECT_NAME=sts-sandbox` still means `sandbox`.
2. Writing to `live` needs `STS_EXPECT_STACK=live` said out loud; no default reaches it.
3. Simulation and sweep scripts (`run_session_simulations.sh`, every `bin/run_*`, `rewind_session.sh`, the other docker-exec writers) refuse unless the target is `sandbox`. The docker-exec ones read the stack name from the container env (`STS_STACK_NAME`) or `/health` before writing.
4. Tests in `tests/` for both clients: default, override, sandbox, refusal on mismatch. No network: stub `/health`.
5. Update the README section on stacks.

Done when tests pass, a sandbox run of `run_catalog_workflow.sh` works without extra env, and the same command against a stub reporting `live` is refused.

### Step 2: remove dead code and `--ck1-test` (agent)

Brief the agent with this page's findings and the exact lists below. Two PRs.

**sts-plugins** (`plugins/hart_layout/hart_warm_start.php`):
- Remove the six uncalled functions.
- Remove `--ck1-test`: the three CK1-test functions, the `run_ck1_test` branch and variable in `hart_run`, the `run_ck1_test` and `ck1_test` defaults in `hart_default_config`.
- Remove the `stop_when_locals_secured` branch, then `hart_locals_secured` if its result is no longer read, and the unreachable `else` in `hart_run_session_work`.
- Remove the stale fallback in `hart_track_scale_available`.
- Keep everything else; the tracked path is in use.
- Checks: `php -l`, `tests/check_generic_plugins.sh`, the two plugin tests. In a sandbox stack: `apply_warm_start.sh` default, `apply_warm_start.sh --tracked`, `begin_session.sh`, `play_operating_session.sh`, then run the `hart_session` workflow once. Compare `hart_summarize` output before and after on the same seed.

**sts-helpers:**
- `bin/apply_warm_start.sh`: drop `--ck1-test` (34, 54, 85-86). `seed/hart_seed_config.json`: drop `run_ck1_test` and the `ck1_test` block (254, 263). README line 117.
- Delete `session/`, `switchlists/`, `sts/*.php` legacy CLIs, `bin/generate_switchlists.sh`, `tools/sanitize_sts_backup_sql.py`.
- Delete the unreferenced files after one more grep across sts-helpers, sts-docker, hart `tools/`, `Makefile`, `wiki/`, `docs/`. bin: `backfill_starting_reports.sh`, `run_demand_queue_wave.sh`, `run_empty_gate_wave.sh`, `run_s10_flow_sweep.sh`, `run_traffic_from_s2_coke20.sh`, `run_traffic_from_s2_levers20.sh`, `run_traffic_from_s3_levers.sh`, `run_traffic_post_south_levers.sh`. tools: `expand_customer_location_codes.py`, `rename_location_codes_v2.py`, `rename_offline_location_codes.py`. diagnostics: `add_fleet_pack`, `add_nvl_nextday_phase`, `apply_cold_ix`, `build_d749_supplement`, `build_staging_board`, `ck1_train_snapshot`, `fix_session2_switchlists`, `heal_s3_switchlist_orphans`, `preserve_session_orders_restore`, `probe_coke_auto_gen`, `refresh_d749_nextday`, `regen_session_switchlists_from_masters`, `run_to_ck1_scale`, `test_run_skip_sections.js`, `validate_session_snapshot`. Keep the five `_probe_*` checks for step 4. Update `diagnostics/README.md`.
- The CK1 weigh scripts (`setup_ck1_weigh_test`, `rewind_ck1_weigh`) were left alone here; the owner had them deleted on 2026-11-20 (see Results).

The agent reports what it deleted, the sandbox results and the summarize diff, then stops before merge.

### Step 4: move the generic parts into sts-docker (dropped by the owner, 2026-11-18)

**4a, main session.** Read sts-docker's `AGENTS.md`/`CLAUDE.md` first. Decide:
- Where the API client lives in sts-docker (for example `bin/lib/sts_api.{sh,py}`) and how sts-helpers sources it afterwards. sts-helpers keeps a thin shim that sources sts-docker's copy, so HART scripts do not change.
- One `bin/sts` CLI over API v1 (begin, play, warm-start, snapshot, run-workflow) versus moving the scripts one by one. Recommendation: one CLI; the scripts are thin wrappers.
- `rewind_session.sh`: drop it for `session_restart` (no API route yet), or move it with the guard and `sts_restore_sql_file`. Ask the owner.
- `verify_sts_runtime.sh`: fix the plugin paths to the sts-plugins mount, then move it.
- `sync_operational_steps.sh`: delete, or make it refuse to overwrite. Ask the owner.
- `paths.sh` dump-name resolvers stay in sts-helpers.
Batch the owner questions in one multiple-choice ask.

**4b, agent.** Brief it with the 4a decisions. One sts-docker PR on `active`: the client and its tests, catalog runners, snapshot, backup and permissions scripts, `verify_sts_runtime.sh`, the five probes merged into one DB-check script, docs in sts-docker's README. Update `bin/sandbox_baseline.sh` to use its own copies. One sts-helpers PR replacing the moved files with shims. Sandbox checks: `sandbox_baseline.sh`, `run_catalog_tests.sh`, `run_catalog_workflow.sh`, a snapshot and restore.

### Close-out

- One hart PR moving the three submodule pointers, plus `wiki/STATUS.md` (remove the Future goals line on this) and this page's status.
- Owner approves on the Mac UAT copy, then `tools/hosts/pi_sts_update.sh`. No hart deploy is needed; the Pi STS updates by git pull.
- Report: PR links, sandbox results, what is left in sts-helpers, the HART names still inside sts-docker.

## Results (2026-11-18)

- **Job 1, UAT check before the Pi deploy:** the Mac matched the Pi row for row (session 5), so no refresh. On UAT at sts-docker 0b644ac / sts-plugins a2884b4: Lock Backups locked `hart_session_pre5` and `hart_session_post5`; Restart offers `hart_session_pre5`; fresh switch lists and waybill 001-001 print "HART Railroad, ..." and no bare "Railroad"; the workflow's Create Backup steps keep `hart_session_pre/mid/scale/post` and a new one defaults to `hart_session_post`; staging jobs are STG-SCULLY and STG-DEMMLER and the switch-list index, wheel reports and session overview match the Pi. Owner said yes; `pi_sts_update.sh` pulled sts-docker b44f2d5 (#20, a browser-test change not in the image) and sts-plugins a2884b4; live `/health` is `live`, session 5.
- **Step 1 (sts-helpers #9):** the guard expects `uat` by default, `STS_EXPECT_STACK` must be `live`, `uat` or `sandbox`, and `live` is reached only when named. Sweeps, `run_session_simulations.sh` and the docker-exec writers (`rewind_session.sh` except `--dry-run`, `rewind_ck1_weigh.sh`, `backfill_*`, `benchmark_home_split.sh`, `apply_shipment_tune.sh`) need the sandbox container and `/health` to say `sandbox`. 25 tests; a sandbox run of `run_catalog_workflow.sh` passed with no override; sweeps refuse the Mac UAT stack.
- **Step 2 (sts-plugins #7, sts-helpers #10):** `hart_warm_start.php` 1998 to about 1580 lines; removed configs (`run_ck1_test`, `ck1_test`, `stop_when_locals_secured`) and secure-locals with no stop mode are now refused before any write (new test). sts-helpers lost 59 files (about 12,000 lines). Sandbox: warm start default and `--tracked` give the same summary before and after.
- **Left over:** `simulate_ck1_weigh.php` and `setup_ck1_weigh_test.php` (used by `rewind_ck1_weigh.sh`) require `track_scale_helpers.php` at the sts root, where it no longer is, so the CK1 weigh rewind is broken (it was before this work). The owner does not need it: checkpoint backups replace it (2026-11-18). The other leftovers were fixed in sts-docker #21 and sts-helpers #11.
- **UAT incident (2026-11-18):** while rechecking #11 an agent passed the sandbox variables as one string, so compose ran the sandbox overrides under the UAT project; the web container's `PROVISION_DATABASE=1` re-provisioned the Mac UAT database. With the owner's yes it was restored from `backups/mac_pre_refresh/sts_db3_mac_20261118-143310.sql` (identical to the Pi, session 5) into a fresh database folder; the wiped one is `database/docker/sts/db.wiped-20261118`. The Pi was not touched. Run the sandbox with `docker compose -p sts-sandbox ...`, never relying on an exported `COMPOSE_PROJECT_NAME` alone.
- **Decision (2026-11-20):** the owner deleted the broken CK1 weigh scripts: `bin/rewind_ck1_weigh.sh` (and its root symlink), `sts/simulate_ck1_weigh.php`, `sts/setup_ck1_weigh_test.php`, plus what only they used (`sts/README.md`, `sts_helpers_docker_cp_legacy_cli` and `LEGACY_STS` in `lib/paths.sh`, the seed-package wrapper, the README row and the sandbox guard test entry). Checkpoint backups replace them. This closes the left-over item above; nothing else is open on this page.
