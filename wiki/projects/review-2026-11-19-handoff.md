# Project review handoff (2026-11-19)

A read-only review of architecture, performance, runtime code and documentation ran on 2026-11-19, followed by five small PRs. This page lists what was found, what was started, and what is left. Findings marked *verified* were traced in code by a second pass; the rest come from one reviewer's reading.

## PRs opened from the review

| PR | What | State at 18:55 on 2026-11-19 |
|---|---|---|
| #695 | Docs: index refresh, two broken links, Pipelines row in `wiki/home.md` | Merged (docs only) |
| #696 | CI: concurrency group for PRs, pip cache | Open, check passed |
| #697 | `signal_coordinator.py` and `panel_status.py` pass the MQTT retain flag explicitly; test fake defaults to retained, as stock does | Open, check passed; deploy to both hosts after merge |
| #698 | `build_cats_panel.py`, `build_signals.py`, `build_docs_index.py` reject unknown arguments; `--help` writes nothing | Open, check passed |
| #699 | ADR index shows amendments (15 rows) | Open, check passed; ADR-002 row reworded from "Superseded in part by 005" to follow the ADR file, owner to confirm |
| #700 | The three Layout Editor test files run as one job in `tools/check.sh` (168 s measured cold on the Mac; 284, 327, 322 s logged in CI before) | Open, check passed |
| #701 | `jmri_cmd_watcher.py` prints handling failures, catches Java exceptions, writes its result through a temp name; first 8 tests | Open, check passed; deploy to both hosts after merge |
| #702 | `publish_draft.py` stops when merge-base with `origin/main` fails, before any write | Open, check passed |
| #703 | `read_tables` refuses duplicate user names within a type (live file has none) | Open |
| #704 | A foreign `enabling` during an unannounced Hold cancels the hand-off (`_enabling_announced`, `_enable_cancelled`) | Open; ownership logic for live signals, owner review first; deploy to both hosts after merge |
| #705 | `make panels` runs the staging mast and staging sync checks (check-only in both modes) before the stages that read them | Open |
| #706 | `hartlib.level_masts.read` validates its header through `read_rows` and refuses duplicate mast names (the 44 live rows read the same) | Draft: `tools/audit/tests/test_le_cutover.py` had not finished locally; mark ready once CI passes |

Every open code PR still owes `/code-review medium` before merge (AGENTS.md); #699 is docs only. #697 and #704 both edit `jmri/scripts/signal_coordinator.py` in different places; merge one, then rebase the other. A `query` on `track/bridge/sml_mode` or a `RESUBSCRIBE` on `track/bridge/cmd` already retained on the broker stays until replaced or cleared.

Nothing was deployed by the review session. Correction to the review: the plan "5.3b" mentions in `wiki/pipelines/schematic-panels.md` and `docs/jmri/TRACK_LENGTHS.md` are right until the 5.3c bring-in, since the schematic inputs still come from 5.3b (`wiki/STATUS.md`).

## Owner decisions

1. **SML boot race.** Pi and Windows booting within about 3 s both take control (`jmri/scripts/signal_coordinator.py:838`); the fix needs an owner identity on a retained topic.
2. **When to deploy the retain-flag change** to both hosts.
3. **#704 open cases:** a foreign `enabling` after this host has announced is still taken as its own echo; a window of a few milliseconds remains between the post-Hold check and the `enabled` publish; an Enable click during a cancelled Hold can start a second enable. Accept, or fold into the lock and state-enum rework.
4. **`archive/`** (34 MB): delete the bulk or keep it. Live code needs none of it; `aaron`, `dispatcher`, `legacy`, `mimic-qa`, `names`, `wiki` have no references at all; `layouts` and `panels` need five doc links fixed first.
5. **Legacy scripts with no caller:** `retarget_dispatcher_traininfo_transits.py`, `apply_nx_layer.py`, `polish_hart_layout_editor.py` in `jmri/layouts/hart/scripts/`. Park or keep. The JMRI startup config was not searched; `tools/audit/tests/test_hart_tables_writers.py` names them.
6. **ADRs** for the operating flag, plan 5.3c as master, staging from the device map and virtual main/upper devices, or declare `wiki/STATUS.md` the record.
7. **Website cache headers:** long-lived caching for `/assets/` images changes the live server config.
8. **`jmri_cmd_watcher.py` log repeat (#701):** a persisting handling failure now prints every 0.5 s in the JMRI log. Rate-limit or accept.
9. **After-edit hook:** dropping the 14 s `unit-jmri` run from `.claude/hooks/check_after_edit.py` moves failures to `check.sh`.

## Not started: runtime on the Pi and Windows

All in `jmri/scripts/signal_coordinator.py` unless named; tests belong in `jmri/layouts/hart/scripts/tests/test_signal_coordinator_behaviour.py`.

| Item | Evidence | Size | State |
|---|---|---|---|
| Abort clears `_busy` under a running disable worker, which can later publish `disabled` over a new enable | `:463`, `:1020-1022` | S | verified |
| Abort runs on the single MQTT callback thread and waits on the Swing thread, stalling all inbound MQTT. Run it on a worker thread | `:1349`, `:611` | S | verified |
| Second run of the script leaves old listeners and the shutdown task, and the visible button stays on the old instance. Detach the previous instance as `mimic_relay.py` does | `:1455`, `:739`, `:282` | S/M | verified |
| `panel_status.py` re-run doubles turnout and mouse listeners (one click toggles twice) | `jmri/layouts/hart/scripts/panel_status.py:46-48` | S | read |
| Stale retained `enabled` after a power cut leaves both hosts Disabled; re-run the take decision when `disabled` arrives while idle | `:852-860` | S | verified |
| `windowClosing` sleeps 3 s on the Swing thread; `_button.setEnabled` is called off it | `:302`, `:362`, `:947`, `:979` | S | read |
| `panel_status.py` rescans all turnouts on `KnownState`, and walks every editor per sync | `:573`, `:184` | S | read |
| Deploy does not check Windows is reachable before the Pi restarts; no ssh multiplexing; package staged twice | `tools/hosts/sync_hart_package.sh:520`, `:212-219` | M | read |
| Untested: shutdown release, Hold sequences, bulk SML set and its timeout, `sts_car_sync` worker thread, `hide_cats_desk_windows` | | M | |

## Not started: checks and CI

| Item | Evidence | Saving |
|---|---|---|
| A merge pays the schematic cache miss twice (PR run, then push to `main`) | `.github/workflows/check.yml:6-7`; 408 s then 406 s logged | about 200 s of runner time per schematic merge |
| Skip the `publish_draft.py --check` redraw when inputs are unchanged (the hash must cover the plugin, graphs and data) | `tools/schematic/publish_draft.py:133-155`; 18.6 s measured | 18 of 25 s of `make panels CHECK=1` |
| Split `unit-jmri` by file for local runs | `tools/check.sh:141` | about 8 s locally |
| Narrow the after-edit hook (owner decision 9) | `.claude/hooks/check_after_edit.py:30-32` | about 14 s per watched edit |
| Cache search thumbnails | `www/scripts/prepare_github_pages.py:535-557` | 0.7 s |

Leave alone: Bash hook latency (69 ms), `tables.xml` parsing (14 ms for 905 KB), the website build (5.5 s), the serial checks (9 s).

## Not started: schematic pipeline code

| Item | Evidence | Size |
|---|---|---|
| `sync_staging_signals.py` edits `tables.xml` and has no tests; nor has `build_staging_masts.py` | `tools/schematic/sync_staging_signals.py:45-127` | M |
| A rerun of `publish()` on a later day restamps the date; a non-zero `git show` in `on_main` is read as "file not on main" | `tools/schematic/publish_draft.py:319` | S |
| `sync_staging_signals.py` failure path in `make panels` was not exercised with a stale CSV; the generic "later steps read what staging-masts writes" line is off for a check-only step | `tools/schematic/build_panels.sh` | S |
| `mimic_relay.py` prints "sent %s without retain" on a branch stock JMRI never reaches, and the message is wrong on stock | `jmri/layouts/hart/scripts/mimic_relay.py:84` | S |
| `intermediate_signal` depends on strand order and renames edges of every `loop_half` strand in the band | `build_cats_panel.py:641-666`, `:679`, `:698` | M |
| Planned DCC addresses come from sort position, so a new switch shifts later ones | `tools/schematic/build_device_map.py:429` | M |

The staging-signal items overlap the staging signal rule work in another session; check with that work before starting.

## Not started: architecture

- Move generator scripts out of `docs/` (43 Python files; `docs/wiring/scripts/refresh_wiring_docs.py` is 1,798 lines) into `tools/`, outputs stay in `docs/`. M.
- Collapse the seven private CSV readers onto `hartlib.railroad.read_rows`: `tools/schematic/le_common.py:87`, `jmri/layouts/hart/scripts/sync_public_name_map.py:127`, `docs/wiring/scripts/refresh_wiring_docs.py:46`, `docs/wiring/scripts/add_main_upper_levels.py:48`, `ops/hart-ops/card_pipeline/intake_stages.py:72`, `ops/hart-ops/card_pipeline/cars.py:82`. S–M.
- Route `tools/audit/check_wiring_crosswalk.py:132` and `check_layout_facts.py:126` through `hartlib.tables`. M.
- Smoke tests for `generate_card_template.py`, `rebuild_local_station_maps.py`, `generate_waybill_cards.py`, `apply_visual_review.py`. L.
- Split `railroad.py` (CSV facts 112-720, class 724-818, invariants 821-1137) and `build_cats_panel.py` (facts 113-203, staging 205-362, levels 364-757, dress 811-895). L, tests first.
- `tools/schematic/publish_draft.py:60` imports upward from `www/scripts`.

## Not started: documentation

- Shorten the operating-flag, PanelPro, redeploy and STS rows of `AGENTS.md` (12.6 KB, loaded every session) to one line plus a link.
- Move dated history from `wiki/STATUS.md` (18 KB) to `STATUS_LOG.md`.
- A check that fails when `docs/INDEX.md` is out of date (after #698, which gives the tool argument handling).

## Not started: website

- Width and height on the 44 `<img>` tags without them; WebP companions for large JPEGs; a 1200 px hero in place of the 1844 px, 364 KB one.
- `defer` on `nav.js` and the other page scripts where load order allows.
- Exam pages are 160–250 KB of inline HTML; move shared CSS and JS to files and load question data from JSON.
- Check `<video>` tags for `preload` and `poster`.
