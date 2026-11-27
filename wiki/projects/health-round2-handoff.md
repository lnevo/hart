# Project health round 2: hand-off (2026-11-21)

Status: done (2026-11-27)

Comes from the 2026-11-21 rescore (8.5/10, up from 8 on 2026-10-31). Organization stayed at 8 because two scripts kept growing, subagents rose to 7.5 while 68% of launches were still `general-purpose`, and a few wiki table cells grew past the point where anyone reads them. The owner chose the options below on 2026-11-21.

| # | Item | Owner's choice |
|---|---|---|
| 1 | Split `jmri/scripts/signal_coordinator.py` (2,256 lines) | Sibling Jython modules, import proven on the Mac first |
| 2 | Split `tools/schematic/build_device_map.py` (1,615 lines) | Three modules |
| 3 | Agents for the jobs `general-purpose` keeps doing | Two new agents, re-measured on 2026-12-05 |
| 4 | Long wiki table cells | Rewrite, plus a check that fails a cell over 80 words |

## How to run this

- Each item is its own PR. Items 1 and 2 are code: `/code-review medium` before merge. Items 3 and 4 are docs and a small check.
- Items 2, 3 and 4 can run in parallel as worktree agents. Item 1 uses the Mac's PanelPro and the hosts, so it stays in the main session.
- A split commit changes no behaviour. It lands only after the tests that cover the code it moves are green.

## 0. First: the cold `check.sh` failure

On 2026-11-21 a cold `./tools/check.sh` on clean `main` ended `FAILED` after 3m21s, and the next two runs passed. The log printed `not stamped: ops/hart-ops/.venv/bin/python changed while the job ran` for `unit-hart-ops`. Find which job failed (rerun cold, `FULL=1`) and fix the cause: a venv rebuilt mid-run, or a flaky test. Size: S.

2026-11-22: two cold `FULL=1` runs failed on different tests. `test_stamp_gate` copied `FULL=1` into its own check.sh call and skipped the stamp branch it tests (fixed in PR #930). `test_panelpro_wrappers` (the SIGINT and SIGHUP cleanup) fails under the full parallel load and in CI, and passes alone; PR #938 fixes the lost signal in `panelpro_session.sh`. The 2026-11-21 log is gone, so which of the two failed then is not known. The venv line is a warning that only leaves `unit-hart-ops` unstamped; it did not recur.

Done 2026-11-22: both fixes merged (PR #930, PR #938).

## 1. `signal_coordinator.py` into sibling modules

The file is one class, `DigiconMqttSml`, of about 1,800 lines, with 135 tests in `jmri/layouts/hart/scripts/tests/test_signal_coordinator_behaviour.py`. It runs on the Pi and Windows from `JMRI_UserFiles/jython/`. No HART Jython script imports a sibling today.

1. **Prove the import.** Add a one-line sibling module and import it from `signal_coordinator.py` on the Mac. Check it loads in PanelPro (`make panelpro-test`) and loads again on a re-run of the script (the re-run path detaches the old instance). If the folder is not on the Jython path, the module puts its own folder on `sys.path`. Stop and report if neither works.
2. **Make the deploy ship the new files.** `sync_hart_package.sh` and the check that lists what ships must include each module. `test_jython_no_print_function` and the other Jython checks must cover them.
3. **Split in this order:**
   - `sml_claims.py`: claim parsing and ordering (`_parse_claim`, `_claim_key`, `_owned_claim` and the claim-race methods). This is plain logic and the easiest to test.
   - `sml_beans.py`: manager and bean lookups (`_mast_manager` to `_bean_label`, `_mast_for_head`, `_sml_for_mast`, the destination maps).
   - `sml_handoff.py`: the enter, disable and hand-off steps (`_enter_enabled` to `_hand_source_to_sml`), if the class still reads poorly after the first two.
   The class keeps MQTT, listeners, the button and shutdown.
4. **Live test** with the owner on both hosts (boot race, toggle, quit release), then deploy `--pi --win` together.

Size: M. Done when the file is under 1,200 lines, the tests pass unchanged, and both hosts run it.

Done 2026-11-22 (PR #933, deployed `--pi --win` at f0e6ac0c): the script is 1,187 lines, with `sml_beans.py`, `sml_claims.py` and `sml_handoff.py` beside it, loaded from `preference:jython` and reloaded on a re-run. A real PanelPro load on the Mac (a copy of the profile on a private broker) matched main's log line for line. On the hosts the Pi loaded the modules, a Windows force claim made it stand down, an operator Enable took Digicon back, and the quit released (Hold, Unheld, disabled) before a clean boot take; Windows stayed Disabled. The boot race was not staged (owner, 2026-11-22: hard to reproduce and covered by the claim tests). Rollback: `make redeploy COMMIT=59811d92`.

The later split (group D: `sml_events`, `sml_quit`, `sml_ui`, `panel_status_clicks`, `panel_status_turnouts`): accepted by the owner without a live test on 2026-11-26 (step 4 not run: no `make panelpro-test`, lamp clicks, SML button or quit release). A failure found later is debugged then.

## 2. `build_device_map.py` into three modules

1. Check `test_build_device_map*` and the device-map guard tests cover the readers and the staging layer. Add tests where a moved function has none.
2. Move the readers (`read_pins`, `wiring_rows`, `read_staging_pins`, `helix_pins`, `read_places`, `frozen_wires`) to `device_map_inputs.py`.
3. Move the staging layer (`staging_layer` to `staging_rows`, about 400 lines) to `device_map_staging.py`.
4. `build_device_map.py` keeps `Nodes`, `build`, `solve` and `main`.
5. Each move is one commit. `make panels CHECK=1` and the device-map check must show byte-identical outputs. Update `pipeline_map.json` for the new files.

Size: M. Done when `build_device_map.py` is under 900 lines and every output is byte-identical.

Done 2026-11-22 (PR #935): `build_device_map.py` is 833 lines, with `device_map_inputs.py`, `device_map_staging.py` and a third module, `device_map_schematic.py`, for the drawing's track helpers, which the 900-line target needed. The builder re-exports every moved name. `make panels CHECK=1` passed all 18 steps and the Layout Editor candidates were byte-identical.

## 3. Two new agents

From 404 `general-purpose` launches between 2026-10-31 and 2026-11-21: about 114 were schematic, Layout Editor, panel or device-map edits, and about 65 were verifying review findings.

- **`schematic-builder`**: edits under `tools/schematic/`, `tools/hartlib/` and the Layout Editor scripts, run in a worktree. Its brief carries the rules agents keep needing: geometry 1:1, `mainline="yes"`, never `fit_panel_*` or `polish_layout_geometry`, approval fingerprints, `make panels CHECK=1`, outputs byte-identical unless the task changes them.
- **`finding-verifier`**: read-only. It gets one claimed bug and the code, and answers confirmed, plausible or wrong, with the line that shows it. It is used to triage `/code-review` and audit findings.
- Add both to the `AGENTS.md` subagent table and update `subagent_guard.py` if it lists agents.
- Built 2026-11-22 (`.claude/agents/schematic-builder.md`, `finding-verifier.md`, table rows added; the guard lists no agents). Not done: the re-measure below is pending.
- **Re-measure on 2026-12-05** with the same transcript count. Target: `general-purpose` under 50% of launches.
- **How to count** (owner, 2026-11-22: run it when the owner asks; every launch counts; compare with 404 and 68%): `python3 tools/ops/agent_launch_count.py --since 2026-11-22 --until 2026-12-05`. It prints two counts: the Agent calls sessions chose, which rebuilds the baseline's method (it gives 426 general-purpose of 620, 68.7%, for 2026-10-31 to 2026-11-21, against the recorded 404 and 68%), and every launch, which adds skill forks such as `/code-review` and their reviewers (911 and 82.4% for the same window). Only the first compares with 404 and 68%.

Size: S.

## 4. Long wiki cells

Twelve table cells run over 80 words. The longest is row 8 of [`source-data-exceptions-handoff.md`](../../archive/history/wiki/projects/source-data-exceptions-handoff.md) at 508 words. Others are in `pipelines/schematic-panels.md` (6), `level-unification-handoff.md` (2), `pipelines/switch-facts.md` (2) and one more in the source-data hand-off.

1. Cut each cell to one to three sentences and move the detail to a section below the table, linked from the cell, as row 10 already does.
2. Add a rule to `check_agent_docs.py` (or the static job's wiki check): a table cell in `wiki/` or `AGENTS.md` over 80 words fails. `STATUS_LOG.md` and `archive/` are exempt, since they hold history.

Size: S. Done when the check passes on `main`.

Done 2026-11-22 (PR #928): all twelve cells cut with their detail in sections below the tables, and `check_agent_docs.py` fails a cell over 80 words.

## Rescores

The rescores (10-31, 11-22 and 11-27), with what was measured and how to measure again, are on the [report cards](../report-cards.md) page.

## Done when

Done 2026-11-27: items 0 to 4 are merged, item 1 is deployed, and the subagent target is met (27% `general-purpose` in the 2026-11-27 rescore), so the 2026-12-05 count is dropped (owner).

All four items are merged, item 1 is deployed to the Pi and Windows, the 2026-12-05 agent count is recorded here, and this page is marked done.
