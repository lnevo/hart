# Leftovers after the loose-ends round (2026-11-27)

Status: active
Coordinator: a background leftovers coordinator of session hart-2d (merge queue, lanes, deploys, dashboard)
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
