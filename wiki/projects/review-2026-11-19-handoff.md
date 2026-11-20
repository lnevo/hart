# Project review handoff (2026-11-19)

A read-only review of architecture, performance, runtime code and documentation ran on 2026-11-19, followed by a round of small PRs and a code review of each. This page lists what was found, what was started, and what is left. Findings marked *verified* were traced in code by a second pass; the rest come from one reviewer's reading.

## State at the end of 2026-11-19

Every code PR below had `/code-review medium` and a fix commit for what the review confirmed, except #712 and the docs-only PRs.

| PR | What | State |
|---|---|---|
| #695, #699, #707 | Docs fixes, ADR index amendments, this page | Merged |
| #696 | CI concurrency keyed on the PR number, pip cache | Merged |
| #697 | Explicit MQTT retain flag in `signal_coordinator.py`, `panel_status.py`, `mimic_relay.py`; needs JMRI 5.9.1 or later | Merged, deployed |
| #698 | Three scripts reject unknown arguments; `--help` writes nothing | Merged |
| #700 | Layout Editor tests as one job in `tools/check.sh` | Merged |
| #701 | `jmri_cmd_watcher.py` answers with an error result on failure | Merged, deployed |
| #702 | `publish_draft.py` stops on a failed merge base or a failed `git show` | Merged |
| #703, #705, #706, #708 | `read_tables` duplicates, staging checks in `make panels`, level masts validation, wiring CSV readers | Merged |
| #704 | SML Hold cancel | Closed unmerged (owner): folded into the boot-race design |
| #709 | Deploy preflight for every named host, also for `redeploy_commit.sh` | Merged |
| #710, #711 | Tests for `sts_car_sync.py`, `hide_cats_desk_windows.py`, `build_staging_masts.py`, `sync_staging_signals.py` | Merged |
| #712 | Width and height on 26 pages' images, `defer` on scripts | Merged |
| #713 | ADRs 025 to 028 (operating flag, plan 5.3c as master, staging from its device map, virtual main/upper devices) | Merged; the owner's reading of the wording is still to come |
| #714 | Three legacy scripts moved to `jmri/layouts/hart/parked/` | Merged, deployed |
| #716 | `check_after_edit.py` runs only the test files that name the edited script | Merged, code-reviewed; website deployed at `3018c9c2` |
| #719 | `panel_status.py`: a re-run detaches the earlier run's listeners; only the changed turnout is updated. The editor-walk finding was mostly wrong and was skipped | Merged, deployed |
| #720 | 33 generator scripts moved from `docs/` to `tools/`; 10 stay in `docs/` (frozen electrical SOQ, speed-matching vendor scripts) | Merged |
| #721 | `signal_coordinator.py`: five runtime fixes (see the runtime table) | Merged, deployed |
| #723 | Site speed: WebP companions, 1200 px hero, exam CSS and JS in files | Merged |
| #724 | CI cache handed from the PR run to `main` through an artifact; `publish_draft --check` stamp; `map_revision` moved into `hartlib`; `unit-jmri` split for local runs | Merged |
| #725 | Check that `docs/INDEX.md` is current | Merged |
| #727 | Five `AGENTS.md` rows shortened, detail into skills | Merged; the owner's reading of the wording is still to come |

Deployed to the Pi and Windows together at `b52742ce` on the night of 2026-11-19. It carries #697, #701, #714, #716, #719 and #721. Afterwards `track/bridge/cmd` held nothing retained and `track/bridge/sml_mode` held `disabled` (the real mode), so the one-off clear step from #697 was not needed.

Open: the SML boot race PR (being written; it does not merge before a live test with both hosts) and AnyRail 5.3c Phase 2 (agent running, see `anyrail-5-3c-handoff.md`).

## Next steps, in order

1. **SML boot race.** Owner decision 2026-11-19: the first timestamp wins, a tie goes by host name. Both hosts must get the new payload in the same deploy since each compares the payload text. Tests in the fake first, then a live test with the owner and both hosts; no merge before that.
2. **AnyRail 5.3c Phase 2** finishes first, because the next two items edit files it touches.
3. **After Phase 2:** move dated history from `wiki/STATUS.md` to `STATUS_LOG.md`; split `railroad.py` and `build_cats_panel.py` (tests first).
4. **Smaller items** in the "Not started" tables below.

## Owner decisions made on 2026-11-19

- `archive/`: keep all of it.
- Website cache headers: leave as they are.
- The leftover `/tmp/hart-pkg.XXXXXX.tgz` on the Mac was deleted.

## Open questions for other work

- Staging signal rule (owned by another session): `signal_number` gives 67/66 at MP 6.6 and 67/68 at MP 6.7, so two pairs a tenth apart share a westward name; the stop is on the tenth, so MP 9.8 westward returns 99 although the message says names stop at 98. Pinned in `test_open_question_...` tests (#711).
- `sts_car_sync.py`: stock `ThreadingUtil.runOnGUI` logs and drops an exception raised off the GUI thread, so a failed batch answers `ok: true, saved: true`. Pinned as a known fault in #710, not fixed.
- A redeploy of a commit that already has the preflight runs it twice.

Done since the lists below were written, so skip them there: the deploy reachability check, tests for the two staging scripts, the `mimic_relay.py` message, the `on_main` `git show` case, the wiring CSV readers (#708), image sizes and `defer` (#712).

Struck as not needed (CSV-readers check): the "seven private CSV readers" item. `sync_public_name_map`, `add_main_upper_levels` and `refresh_wiring_docs` already moved; `le_common.read_csv` and the `card_pipeline` `intake_stages` and `cars` readers need every column unstripped, and hart-ops does not import `hartlib`. Also struck: routing `check_wiring_crosswalk` and `check_layout_facts` through `hartlib.tables`; they already use it, and the element walks that remain need new accessors.

Correction to the review: the plan "5.3b" mentions in `wiki/pipelines/schematic-panels.md` and `docs/jmri/TRACK_LENGTHS.md` are right until the 5.3c bring-in, since the schematic inputs still come from 5.3b (`wiki/STATUS.md`).

## Not started: runtime on the Pi and Windows

All in `jmri/scripts/signal_coordinator.py` unless named; tests belong in `jmri/layouts/hart/scripts/tests/test_signal_coordinator_behaviour.py`.

| Item | Evidence | Size | State |
|---|---|---|---|
| Abort clears `_busy` under a running disable worker, which can later publish `disabled` over a new enable | `:463`, `:1020-1022` | S | Done (#721) |
| Abort runs on the single MQTT callback thread and waits on the Swing thread, stalling all inbound MQTT. Run it on a worker thread | `:1349`, `:611` | S | Done, #721 |
| Second run of the script leaves old listeners and the shutdown task, and the visible button stays on the old instance. Detach the previous instance as `mimic_relay.py` does | `:1455`, `:739`, `:282` | S/M | Done, #721 |
| `panel_status.py` re-run doubles turnout and mouse listeners (one click toggles twice) | `jmri/layouts/hart/scripts/panel_status.py:46-48` | S | Done, #719 |
| Stale retained `enabled` after a power cut leaves both hosts Disabled; re-run the take decision when `disabled` arrives while idle | `:852-860` | S | Done, #721 |
| `windowClosing` sleeps 3 s on the Swing thread; `_button.setEnabled` is called off it | `:302`, `:362`, `:947`, `:979` | S | Done (#721) |
| `panel_status.py` rescans all turnouts on `KnownState`, and walks every editor per sync | `:573`, `:184` | S | Done, #719 (per-turnout update; editor walk skipped) |
| Deploy does not check Windows is reachable before the Pi restarts; no ssh multiplexing; package staged twice | `tools/hosts/sync_hart_package.sh:520`, `:212-219` | M | read |
| Untested: shutdown release, Hold sequences, bulk SML set and its timeout, `sts_car_sync` worker thread, `hide_cats_desk_windows` | | M | |

## Not started: checks and CI

| Item | Evidence | Saving |
|---|---|---|
| **Done, #724.** A merge pays the schematic cache miss twice (PR run, then push to `main`) | `.github/workflows/check.yml:6-7`; 408 s then 406 s logged | about 200 s of runner time per schematic merge |
| **Done, #724.** Skip the `publish_draft.py --check` redraw when inputs are unchanged (the hash must cover the plugin, graphs and data) | `tools/schematic/publish_draft.py:133-155`; 18.6 s measured | 18 of 25 s of `make panels CHECK=1` |
| **Done, #724.** Split `unit-jmri` by file for local runs | `tools/check.sh:141` | about 8 s locally |
| **Done, #716.** Narrow the after-edit hook (owner decision 9) | `.claude/hooks/check_after_edit.py:30-32` | about 14 s per watched edit |
| Cache search thumbnails | `www/scripts/prepare_github_pages.py:535-557` | 0.7 s |

Leave alone: Bash hook latency (69 ms), `tables.xml` parsing (14 ms for 905 KB), the website build (5.5 s), the serial checks (9 s).

## Not started: schematic pipeline code

| Item | Evidence | Size |
|---|---|---|
| **Done, #711.** `sync_staging_signals.py` edits `tables.xml` and had no tests; nor had `build_staging_masts.py` | `tools/schematic/sync_staging_signals.py:45-127` | M |
| **Done, #702** (the `git show` case). A rerun of `publish()` on a later day restamps the date; a non-zero `git show` in `on_main` is read as "file not on main" | `tools/schematic/publish_draft.py:319` | S |
| `sync_staging_signals.py` failure path in `make panels` was not exercised with a stale CSV; the generic "later steps read what staging-masts writes" line is off for a check-only step | `tools/schematic/build_panels.sh` | S |
| **Done, #697.** `mimic_relay.py` prints "sent %s without retain" on a branch stock JMRI never reaches, and the message is wrong on stock | `jmri/layouts/hart/scripts/mimic_relay.py:84` | S |
| `intermediate_signal` depends on strand order and renames edges of every `loop_half` strand in the band | `build_cats_panel.py:641-666`, `:679`, `:698` | M |
| Planned DCC addresses come from sort position, so a new switch shifts later ones | `tools/schematic/build_device_map.py:429` | M |

The staging-signal items overlap the staging signal rule work in another session; check with that work before starting.

## Not started: architecture

- **Done, #720** (33 moved, 10 stay in `docs/`). Move generator scripts out of `docs/` (43 Python files; `docs/wiring/scripts/refresh_wiring_docs.py` is 1,798 lines) into `tools/`, outputs stay in `docs/`. M.
- **Struck, not needed** (see above). Collapse the seven private CSV readers onto `hartlib.railroad.read_rows`: `tools/schematic/le_common.py:87`, `jmri/layouts/hart/scripts/sync_public_name_map.py:127`, `docs/wiring/scripts/refresh_wiring_docs.py:46`, `docs/wiring/scripts/add_main_upper_levels.py:48`, `ops/hart-ops/card_pipeline/intake_stages.py:72`, `ops/hart-ops/card_pipeline/cars.py:82`. S–M.
- **Struck, not needed** (see above). Route `tools/audit/check_wiring_crosswalk.py:132` and `check_layout_facts.py:126` through `hartlib.tables`. M.
- Smoke tests for `generate_card_template.py`, `rebuild_local_station_maps.py`, `generate_waybill_cards.py`, `apply_visual_review.py`. L.
- Split `railroad.py` (CSV facts 112-720, class 724-818, invariants 821-1137) and `build_cats_panel.py` (facts 113-203, staging 205-362, levels 364-757, dress 811-895). L, tests first.
- `tools/schematic/publish_draft.py:60` imports upward from `www/scripts`.

## Not started: documentation

- **Done, #727.** Shorten the operating-flag, PanelPro, redeploy and STS rows of `AGENTS.md` (12.6 KB, loaded every session) to one line plus a link.
- Move dated history from `wiki/STATUS.md` (18 KB) to `STATUS_LOG.md`.
- **Done, #725.** A check that fails when `docs/INDEX.md` is out of date (after #698, which gives the tool argument handling).

## Not started: website

- **Done, #712 and #723.** Width and height on the 44 `<img>` tags without them; WebP companions for large JPEGs; a 1200 px hero in place of the 1844 px, 364 KB one.
- **Done, #712.** `defer` on `nav.js` and the other page scripts where load order allows.
- **Done, #723.** Exam pages are 160–250 KB of inline HTML; move shared CSS and JS to files and load question data from JSON.
- Check `<video>` tags for `preload` and `poster`.
