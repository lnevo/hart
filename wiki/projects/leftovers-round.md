# Leftovers after the loose-ends round (2026-11-27)

Status: done (2026-11-27)
Dashboard: https://claude.ai/artifact/DiMs49NdBzpTiH9Bq1FiSe

The owner asked on 2026-11-27 to finish the "Left after the loose ends" list in [wave-loose-ends.md](wave-loose-ends.md). The changed files are regraded at the end, and the [report card](https://claude.ai/artifact/2feCxg41LpAFfoP3e6Z8nE) is republished only if the average rises above 3.297 (owner).

## Lanes

| Lane | Scope | Agent | Ships |
|------|-------|-------|-------|
| LO-L1 Deploy and host scripts | `pi_quit_panelpro.sh` and `build_image.sh` refuse unknown arguments; `win_run.sh` without dated comments and its 160-line heredoc split; `gate.sh` dated comment; a `ci_pass.py` crash before its handler still prints the not-blocking line; `ci_pass.py`'s GitHub records typed; `test_deploy_stage.py` and the other deploy tests run the scripts against a temporary JMRI profile instead of grepping source or reading `~/JMRI` | `tool-fixer`, opus | Pi, Windows |
| LO-L2 Regrade faults | `cars.py` returns non-zero after a failed STS step; `check_stamps.py` parses its arguments with argparse; `common.sh` without dated comments; `run_native_sml_qa.py` checks `mosquitto_sub`'s return code | `tool-fixer`, opus | as `live_paths.txt` says |
| LO-L3 Site JS | a shared warrant scene in `www/js/track-warrant.js` used by the exam and play (text unchanged); `run-tto.js` with clear names and constants; an unknown key in `signals.js` gives a named error | `site-builder`, opus | site |
| LO-L4 Small items | `PUBLICATION` in `rebuild_crew_instructions.py` read on use; the coordinate skill's step 5 says `gh run list --commit` needs the full 40-character SHA | `tool-fixer`, sonnet | nothing |
| LO-RC Regrade | regrade the changed files after the last merge, parked code left out; republish only if the average rises | `repo-auditor`, opus | nothing |

## How to run this

- The merge rules of [ADR-042](../decisions/ADR-042-strict-off-main-push-run-watched.md): merge `main` into a PR only on a conflict or a stale check, locally for files with merge drivers; watch main's push run after each merge; nothing deploys while main is red.
- Each lane passes the handoff skill's gates: one full `make remote` per PR, a review, every finding through `finding-verifier`.
- At most 4 lanes at once beside the other sessions.

## Done when

Every lane is merged and deployed, the regrade is done (and the card republished only if it rose), and this page is `Status: done`.

## Result

Coordinated by hart-55 from 16:23 (hand-off from hart-2d). Every lane merged; main's push run passed after each merge.

| Lane | PR | Merge | Shipped |
|------|----|-------|---------|
| Size caps with headroom, health round 2, this plan | #1364 | c948929a3 | nothing |
| LO-L2 regrade faults and LO-L4 small items | #1365 | 75d10992a | nothing |
| LO-L3 site JS | #1367 | 2b371a670 | site, 17:26, Build counts unchanged |
| LO-L1 deploy and host scripts | #1368 | 2f14be300 | nothing (no file under `live_paths.txt`) |

- `PUBLICATION` in `rebuild_crew_instructions.py` was already read on use (3a9e2324a); the module-level reads left are in `rebuild_dispatcher_train_list.py`, `rebuild_yardmaster_sequence.py`, `rebuild_station_map.py` and `rebuild_operator_primer.py`.
- No fake-writer test for #1361's cause: `deploy_status.sh` now uses a here-string, so no pipe is left to test.
- Regrade (LO-RC): 34 changed code files read again at 2f14be300 by two repo-auditors. The average rose from 3.297 to 3.298 (222 grade-point-lines under B+, from 402), so the [report card](https://claude.ai/artifact/2feCxg41LpAFfoP3e6Z8nE) was republished with an "After the leftovers" section. Six source files up a step, three down (`check.sh`, `run_native_sml_qa.py`, `run.js`).
- The closing PR ran `make baselines`: the mypy and habits baselines went down, `py_sizes.csv` and `hand_tables.csv` were already current.

### Left after the leftovers

- `run_native_sml_qa.py` restores only topics that had a retained value (Switch 7's feedback topics stay set after a run), and `pub()` shows a traceback when `mosquitto_pub` fails.
- `check.sh` runs manifest lines through `eval`; `run.js`'s three random streams are all `Math.random`; `track-warrant.js` inserts `opt.intro` unescaped.
- `check_py_sizes.py` keeps two dated comments; `check_stamps.py` is at 791 of 800 lines; `check_data_readers.py` copies hartlib's tracked-files helper.
- Tests: `test_check_stamps.py` has dated comments and two source greps; `test_deploy_stage.py` keeps its PowerShell and rsync source reads; the deploy tests copy each other's ssh and git helpers; `test_signals_keys.py` repeats the node-runner wrapper.
- Stopping `make remote` on the Mac leaves its run going on the Windows box: the remote bash outlives the killed ssh, so its `~/wt` folder and processes stay until cleared by hand.
