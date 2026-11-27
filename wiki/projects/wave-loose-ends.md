# Loose ends after the code-quality waves (2026-11-27)

Status: done (2026-11-27)
Dashboard: https://claude.ai/artifact/P7sr9F2vXPUJnWfwxfYKAZ

The owner asked on 2026-11-27 to clean up the "Left after the waves" list in [code-quality-wave.md](code-quality-wave.md#left-after-the-waves). The wave's rulings still hold ([Owner's choices](code-quality-wave.md#owners-choices-2026-11-26)): deploy each merge that ships, parked code stays as it is, ruff stays on F rules only.

## Lanes

| Lane | Scope | Agent | Ships |
|------|-------|-------|-------|
| LE-L1 Hosts and deploy | The Windows apply reads `tools/hosts/pi/jython_scripts.txt` instead of its own list; `audit_panel_graph` loads `panel_counts.json` on use and names a broken file; `ship_mac.sh` stops on a missing listed script; `stage.sh` `stage_package` (about 123 lines) split | `tool-fixer`, opus medium | Pi, Windows |
| LE-L2 Schematic | `le_tables` explicit names instead of a module `__getattr__`; `render_le_layout` honours or refuses `--labels` and `--scale` with `--all-views`; `staging_device_map.load()` takes one typed options record instead of 9 parameters; `staging_rows` returns its drawn dict; `cell_of` takes ASCII digits only. `make panels CHECK=1` byte-identical | `schematic-builder`, opus high | nothing |
| LE-L3 Exam answers off eval | `build_exam_answers.js` stops running the game's source with `Function()` and `with()`: the tables it needs come from a data module the game loads too; `render()` (about 114 lines) split. Answer pages byte-identical | `site-builder`, opus high | site |
| LE-L4 Exam run files | `run-signals.js` `startSIG` (about 195 lines) split; `run-modern.js` track warrant copy uses `play/warrant.js` `copy()`; the 1949 run's own `arriveTTO` path onto `take` and `give`; the packed style in `run-*.js` reformatted. Starts after LE-L3 merges (same files) | `site-builder`, opus medium | site |
| LE-L5 Jython | `le_names.py` stops cutting functions out of `signal_coordinator.py` with regexes and `exec()`: the functions move to a plain module both import (Jython 2.7 compatible, no `hartlib`); `sml_ui.py` broad excepts narrowed and long Swing functions split; one `_log_once` for `sml_beans` and `panel_status_turnouts` | `tool-fixer`, opus high | Pi, Windows |
| LE-L6 Site pages | `fleet.js` uses `photo-viewer.js` as `archive.js` and `gallery.js` do; `www/README.md` names `photo-viewer.js`; `jmri_additions_page.py` chains `from e` (lines 103, 208); `levels_page` `read_meta` checks the `levels_meta.json` shape | `site-builder`, sonnet medium | site |
| LE-L7 Tests and errors | Tests that assert on source text become behaviour tests (`test_speedmatch_offline`, `test_check_docs_only`, `test_build_tables`, `test_layout_docs`, `test_mimic_web`; `test_exam_answers` goes with LE-L3); dated owner notes out of `test_build_cats_panel_bindings` and `test_devices` docstrings; `freeze_wiring` names its OSError and the `pin_row` IndexError; `unit-portal` declares only what its suites read | `tool-fixer`, sonnet medium | nothing |
| LE-L8 WiThrottle client | Read-only: find what opens port 12090 on the Pi about every 5 minutes (a 4-minute watch saw no peer) | `panel-tracer` | nothing |
| LE-RC Report card | After the last merge, regrade the changed files and republish the final card (parked code left out) | `repo-auditor` | nothing |

Not lanes: the mimic's "waiting" state (by design), the parked `occupancy_lamps_display_only.py`, `lcos_rule`'s `exec` (kept), and `play/answers.html`'s share card (owner kept it). `PUBLICATION` in `rebuild_crew_instructions` goes with the table moves.

## Result

Every lane merged; the last at 14:21. Agents and models as run (the plan table above was the starting brief; LE-L9 and LE-L10 ran on `data-lane`, the ADR-039 data-masters agent, which fits better than `tool-fixer`).

| Lane | PR | Agent, model | Merge | Shipped |
|------|----|--------------|-------|---------|
| LE-L1 Hosts and deploy | #1347 | tool-fixer, opus | 0b1ea71f | Pi, Windows (Windows now installs from the shared Jython list), site |
| LE-L2 Schematic | #1341 | schematic-builder, opus | 9fb9c0b8 | site (restamped LE PNG) |
| LE-L3 Exam answers off eval | #1339 | site-builder, opus | fcdf9cca | site (`www/exam/run-data.js`) |
| LE-L4 Exam run files | #1344 | site-builder, opus | d3e3a953 | site (`www/exam/run-tto.js`); the warrant `copy()` reuse was dropped (owner) |
| LE-L5 Jython | #1343 | tool-fixer, opus | 36146975 | Pi, Windows (`jmri/scripts/sml_lcos.py`), site |
| LE-L6 Site pages | #1342 | site-builder, sonnet | 6363ae01 | site |
| LE-L7 Tests and errors | #1346 | tool-fixer, sonnet | 49d3073f | nothing; `unit-portal` stays whole (node and bash reads are untraced) |
| LE-L8 WiThrottle client | none | panel-tracer, sonnet | | finding: this Mac's own netmon.py cron probes port 12090 every 5 minutes; owner: leave it ([not-pending](../not-pending.md)) |
| LE-L9 Table moves A | #1350 | data-lane, opus | b0cb9d00 | Pi, Windows: train card roads and numbers from `trains.csv` (a `HART` row in `roads.csv`), mimic plants from `stations.csv`, native SML QA steps in `native_sml_qa.csv`; QA Switch 7 now drives its feedback sensors (owner) |
| LE-L10 Waybill master | #1349 | data-lane, opus | c92acec1 | site: spot rules, parties and empty returns in data files, interchange cards read from `HART_Spot_Waybills.csv`; the generator writes its deck list to the output folder, never the master; the report balance line is CSX 11, POHC 13 (owner) |
| LE-L11 Table moves B | #1348, #1352 | schematic-builder, opus; site-builder, opus | 6509b7c3, 83a27225 | site: status lamps in `panel_lamps.csv`, layout docs labels in `layout_docs_labels.csv`, roster card rows in `share-cards.json` |
| LE-L12 Local check.sh | #1351 | tool-fixer, opus | bf5ef95b | nothing: the stamp-audit hook hid Homebrew's sitecustomize, so PIL went missing under CHECK_AUDIT; both audit hooks now share `tools/audit/trace_hook/hook_chain.py` |
| LE-L13 Card follow-ups | #1356 | site-builder, opus; tool-fixer, opus | 189d6da0 | site: the additions page uses `hartlib.coordinator.lcos_rule`, `signals.js` is a data module the exam key requires, `check_sml_invariants.py` reports instead of exiting |

Merge runners were general-purpose agents (sonnet, opus for logic). Every PR passed one full `make remote` before it opened (LE-L1, LE-L5, LE-L7, LE-L9, LE-L10, LE-L11b a second to confirm a fix), and `/code-review` high or medium; each non-nit finding went through `finding-verifier`. Review fixes: LE-L5 (the SML button retry stopped on a Python error), LE-L7 (a leaked run marker was not seen), LE-L10 (the generator overwrote the master it reads).

Peer PRs in the same queue: #1336, #1337, #1338 and #1345 (hart-ce), #1340 (dashboards open dark), #1353, #1354 and #1355 (hart-9a check speed-ups), #1357 (ADR-041, bookkeeping files merge without conflicts) #1358 (deploys stop on a red main), #1359 (merge rules with `strict` off, ADR-042), #1361 (no `grep -q` at the end of a pipe under pipefail) and #1362 (hart-ce: one main-red call in the deploy scripts, no dated text). The owner turned `strict` off on main at 14:55. Deploys: Pi and Windows after #1343 (12:13), #1347 (12:33), #1350 (13:04) and at 189d6da0 (14:25), each after the PanelPro smoke test, with the strict audit passing and the Pi log clean; the site after every lane that ships it, Build counts unchanged apart from two new files (`run-data.js`, `run-tto.js`, files 1432 to 1434).

Report card ([final card](https://claude.ai/artifact/2feCxg41LpAFfoP3e6Z8nE), section "After the loose ends", main c50fd6b8): 149 changed scripts read again, the deploy scripts twice. The average is 3.297 (wave 6: 3.301), 402 grade-point-lines under the B+ line; no C or D source files are left (wave 6: 2). `build_exam_answers.js` C+ to B+, `le_names.py` C+ to B-; nine files up, seventeen down, mostly closer reads of lightly touched files. Six deploy and host scripts lost 440 grade-point-lines against wave 6 (`pi_quit_panelpro.sh` A- to B, `win_run.sh` B+ to B, `gate.sh`, `deploy_hartrailroad.sh`, `deploy_status.sh` and `build_image.sh` A- to B+); without those drops the average would be just over 3.3. #1362 brought `ci_pass.py` back to A-.

Also closed: the Windows remote clone's stale `gc.log` (owner): renamed, `git gc` clean.

### Left after the loose ends

- A shared warrant scene in `www/js/track-warrant.js` (LE-L4 kept `run-modern.js`'s own copy, owner).
- `PUBLICATION` in `rebuild_crew_instructions.py` is still read at import (the table moves did not include it).
- Deploy tests (`test_deploy_stage`, `test_redeploy_commit`) read the real `~/JMRI` profile and failed once on a leftover `profile.xml.hart-run.bak` from a PanelPro smoke run; they should use a temp copy.
- From the regrade: `cars.py` returns 0 after a failed STS step; `check_stamps.py` parses argv by position; `common.sh` keeps dated comments and its own parked script list; `run_native_sml_qa.py` ignores `mosquitto_sub`'s return code and leaves Switch 7's feedback topics set after a run when they had no retained value; `check_data_readers.py` copies hartlib's tracked-files helper; `run-tto.js` is B- (terse names, magic numbers); an unknown key in `signals.js` is a raw TypeError.
- Review nits kept: the hook chain loads outside the hooks' try; `layout_docs_labels.csv` cells are not stripped; the QA step texts keep the old DCC numbers beside the switch numbers; `docs/parked/UNPARK.md` row 10 does not say that `check_sml_invariants.py` now fails when NX is unparked (parked docs, left as they are).
- The deploy scripts after #1362: a crash of `ci_pass.py` before its own handler goes on with only the Python traceback; `gate.sh` keeps a dated comment; `ci_pass.py`'s GitHub records are bare dicts. `test_deploy_stage.py` is C+: several tests search shell source instead of running it.
- `pi_quit_panelpro.sh` and `build_image.sh` do not refuse unknown arguments (a mistyped flag to `pi_quit_panelpro.sh` quits PanelPro); `win_run.sh` keeps dated comments and a 160-line remote heredoc.
- Main's push run on 82d48221 failed once in `test_deploy_status` `test_dirty_and_unknown_commit` (the dirty warning missing) and passed on rerun. Likely cause (read from the bash source, not reproduced on Linux): bash 5 writes the stamp in two `write()` calls, `grep -q` matches `dirty=yes` in the first and exits, the second write takes SIGPIPE, and pipefail skips the warning. The Mac's bash 3.2 writes it in one call, so Mac loops never fail. #1361's here-strings remove the pipe.
- The coordinate skill's step 5 gives `gh run list --commit <merge sha>` without saying the SHA must be the full 40 characters; a short one returns nothing (hart-9a).

## Waiting on the owner

Nothing. The eight table moves and the waybill master were decided at 11:15 to 12:10 and done in LE-L9 to LE-L11.

## How to run this

- At most 4 lanes at once, so the coordinator, its lanes, the merge runner and other sessions stay under the 8-session cap. LE-L4 waits for LE-L3.
- Each lane passes the "no failed PRs" gates in the [`handoff`](../../.claude/skills/handoff/SKILL.md) skill before its PR opens: one full `make remote` per PR, a second only to confirm a fix, no `FULL=1`.
- Every code finding goes through `finding-verifier` before it is fixed. Review fixes on an open PR go to the general-purpose merge runner in that PR's worktree, not to a named agent.
- One merge at a time; the coordinator deploys each merge that ships (`deploy` skill) and keeps every dashboard row current.

## Done when

Every lane is merged and deployed or moved to the owner list with its reason, the report card is republished, and this page is `Status: done`.
