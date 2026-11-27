# Loose ends after the code-quality waves (2026-11-27)

Status: active
Coordinator: a background loose-ends coordinator of session hart-2d (merge queue, lanes, deploys, dashboard)
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

## Waiting on the owner

- The eight live table moves: `train_cards.py` `TRAINS`, `lcos_mqtt_mimic.py` `PLANT_ORDER`, `run_native_sml_qa.py` `OCC`, `TO` and `SCENARIO`, `panel_items.py` `STATUS_BEANS`, `build_layout_docs.py` `LABELS`, `panel_image.py` `ROSTER_ROWS`. Each moves to a data file or stays with a name check.
- The waybill master: the 7 `waybill_data.py` rows in `tools/audit/hand_tables.csv`.

## How to run this

- At most 4 lanes at once, so the coordinator, its lanes, the merge runner and other sessions stay under the 8-session cap. LE-L4 waits for LE-L3.
- Each lane passes the "no failed PRs" gates in the [`handoff`](../../.claude/skills/handoff/SKILL.md) skill before its PR opens: one full `make remote` per PR, a second only to confirm a fix, no `FULL=1`.
- Every code finding goes through `finding-verifier` before it is fixed. Review fixes on an open PR go to the general-purpose merge runner in that PR's worktree, not to a named agent.
- One merge at a time; the coordinator deploys each merge that ships (`deploy` skill) and keeps every dashboard row current.

## Done when

Every lane is merged and deployed or moved to the owner list with its reason, the report card is republished, and this page is `Status: done`.
