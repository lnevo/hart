# Code-quality wave (2026-11-26)

Status: active (wave 5 done 2026-11-27 06:35; wave 6 running from 06:40)
Coordinator: wave 6 coordinator (a background agent of hart-e0), from 2026-11-27 06:36 (holds the merge queue and the deploys; took over from the wave 5 coordinator)
Dashboard: https://claude.ai/artifact/XbLG38xfSzSdbE4eoutFQ7 (lanes, events and agents, kept live by the background coordinator)

A read-only review on 2026-11-26 graded the repo's 781 scripts at B- overall. The code was decent, with recurring AI habits:
- helpers copied between files until the copies drift
- `str(exc) from None`, which drops the traceback
- dated history in comments
- tests that search source text instead of running it
- annotations that no checker runs
- records kept in bare dicts and tuples

It also found a bug: the operating-flag guard missed `$(ssh …)` and `xargs ssh`. This wave fixes those habits and reviews every C- and D-graded file. The AGENTS.md "Scripts" rules (#1225) cover new code.

## Owner's choices (2026-11-26)

- **History notes:** delete a note when an ADR, a wiki page or git already records the decision. Move a decision that only the comment records into the wiki. Keep the why in the code, without dates.
- **mypy:** strict for hartlib. Every other CPython folder runs in basic mode against a per-file baseline that may only go down. Jython is excluded.
- **Parked code:** `gen_ctc_track_plan.py` and the parked rules in `refresh_bean_comments.py` stay as they are.
- **Parked code in the report card (2026-11-27):** parked code is left out of the card: not in the line-weighted average, the C and D counts or the files read. The card lists parked files separately, each with a one-line reason. Parked means everything under jmri/layouts/hart/parked/ and the scripts that serve only parked features (hartlib.parked.PARKED: nx, dispatcher, uss), each confirmed from its callers; a file that serves live and parked code is graded.
- **Last wave (2026-11-27):** wave 6 is the last wave; its card is the final one.
- **Guard against regressions:** a ratchet check (`check_habits.py`) plus the AGENTS.md rules. ruff stays on F rules only.
- **Deploys:** deploy each merge that ships straight away, with no live try ("just deploy, consider everything tested").

## Lanes

| Lane | Scope | PR |
|---|---|---|
| L0 | AGENTS.md and handoff rules | #1225 merged |
| L1 | Guard parser: one shared `shell_parse.py` for main_guard and subagent_guard | #1227 merged |
| L2 | hartlib types and the mypy check | #1233 merged |
| L4 | tools/ drift, the habits ratchet, the C and D files in tools/ | #1231 merged |
| L5a | ops drift (colours, OOXML, shim) and car and waybill types | #1228 merged |
| L6a | jmri source-grep tests, sml_handoff, the C and D files in jmri/ | #1229 merged |
| L3 | tools/schematic types and C and D files (after L2) | #1236 merged |
| L5b | publications and station maps C and D files (after L5a) | #1234 merged |
| L6b | speedmatch C and D files | #1230 merged |
| L7 | www/scripts, exam and play C and D files | #1232 merged |

Other PRs: wave page #1226, wiki decisions #1235, bridge docs #846. All merged.

## Result

- The report card went from B- (2.86) to B (3.03). C and D files went from 64 to 33.
- mypy runs in `check.sh` and CI, with hartlib strict and clean. `check_habits.py` and a mypy baseline ratchet every other file. Counts that fall pass with a note.
- Shipped: #1229 and #1230 to the Pi and Windows, and #1232 to the site. The Windows LcosBridge task and its logon tabs were removed, so the bridge runs on the Pi.

## Left after wave 1

Wave 2 (below) closed every item here except the WSL venv note and the parked `gen_ctc_track_plan.py`.

- publications: the station-map and rebuild scripts still have long drawing functions. `rebuild_station_map.py` is a D.
- tools/schematic: `build_device_map.build` (324 lines), `device_map_staging.staging_rows` (205) and `build_layout_le.build` (160).
- `build_cats_panel.py` still calls `sys.exit` about seven times.
- `Switch.level` callers need hartlib's `Switch.level` moved from `LevelText` to `Level` first.
- `run.js` and `play.js` share globals and duplicate the source tables.
- The exam clock shows 24:01 past midnight.
- `www/behind/jmri-additions.html` does not list the DecoderPro roster (`roster.xml`, `jmri/layouts/hart/roster`).
- Each `requirements.txt` bump must be installed by hand in the Windows WSL venv (`uv pip install --python .venv/bin/python ...`).
- `docs/jmri/speedmatching/profile-2026-11-08/block_speeds.py` is proposed for the archive.
- `gen_ctc_track_plan.py` stays as it is, because it is parked.

## Wave 2 (2026-11-26)

A read-only sweep graded the 362 files that wave 1 had graded from metrics only (3 auditors): 12 A, 71 A-, 110 B+, 84 B, 36 B-, 25 C+, 3 C, 2 D, 19 parked. The bugs it found went to the tier 3 lanes. Every PR passed the six "no failed PRs" gates (handoff skill, Merge) before it opened.

| Lane | What | PR | Ships |
|---|---|---|---|
| A | SM-01 drawing split; shared compass, fonts and sheet kit; typed EQ-01 and crew sheets | #1240 | nothing |
| A2 | Local station map drawers, primer text in data, TT-23, CC label, full map | #1244 | nothing |
| B | Typed mast plan and CATS binding records | #1242 | nothing |
| B2 | LE and device-map builds in typed stages | #1245 | nothing |
| C | One source table for both games; the Extra East clock wraps to 0:01 (owner); typed tables page | #1243 | site |
| D1 | Typed speedmatch analyze; `speed-by-step` replaces `block_speeds.py` (archived), CSV byte-identical (owner) | #1247 | Pi, Windows |
| D2 | Shared film helper, typed levels_svg, frozen promo format, typed mimic loader | #1241 | Pi, Windows (mimic) |
| E | Device master rows are `DeviceRow` records; `Switch.level` is a `Level` | #1256 | nothing |
| F2 | Named errors instead of SystemExit: card pipeline, www/scripts, levels page, wiring | #1249 | nothing |
| F1 | Named errors instead of SystemExit: tools/schematic | #1254 | nothing |
| G | Jython parts and traced/orient parts as real modules; the Turnouts lamp found by tooltip (owner: ship it) | #1246 | Pi, Windows, site |
| H | tools/audit held to mypy strict; `check_mypy` reads the strict folders from `mypy.ini` | #1259 | nothing |
| T3a | Host-script bugs (STS dump prune, unset ROOT, snapshot); retired-file deletes dropped, Start Up strip kept and extended to Windows per-computer profiles (owner) | #1250 | Pi, Windows |
| T3c | Mimic view escaping, launch_cats folder, retain clear, turnout feedback, dead code | #1251 | Pi, Windows |
| T3d | Card pipeline: sharpen folders, two scripts archived (owner), shared sticker-grid helpers and road table | #1253 | nothing |
| T3s | Test-loop values from the AnyRail 5.3c plan (owner); typed `correct.py` | #1255 | nothing |
| T3e | Missing Pillow, search thumbs, route lookup, promo and worktree exits; `build_masts.file_rows` split | #1257 | nothing |
| T3p | CATS 3.2 zip pinned by sha256 (owner) | #1258 | nothing |

Decisions found only in comments, recorded here:
- A home mast at no switch is an anchor mast, by one rule on every level (was in `build_masts.py`).
- The step runners never treat BS W-1 and W-2 (the Brick yard spurs off Switch 3) as route sensors (`jobkit.NOT_ROUTE`).
- `generated_desk_header.xml` was frozen from the live desk on 2026-11-15 (was in `cats_panel_dress.py`).

Report card after wave 2 (https://claude.ai/artifact/2feCxg41LpAFfoP3e6Z8nE): the line-weighted average went from 2.86 at the start to 3.03 after wave 1 and 3.12 after wave 2 (B). C and D files went 64, 33, 16, with none at D. A-range files went 8, 18, 133. Reviewers have now read 469 of 489 source files.

### Left after wave 2

- The 16 C files: the card-pipeline generators, the three station-map renderers, two publication rebuilds, two share-card recipes, `render_cats_panel`, `cs105_consist` and `export_track_lengths`.
- mypy strict: tools/ops (96 errors in 17 files) and tools/schematic (442 in 42), one folder at a time.
- `paths.exit_if_overridden` and `tables_build.refuse_generated` still exit (about 20 callers, some parked); `hartlib.hosts` still exits, because the MQTT tools and the mimic read it at import (each entry script must catch a named error first); `evolution.py`; `render_le_layout.py` is at its size limit.
- About 100 callers still read device rows by key through `DeviceRow`'s mapping view.
- `block_lengths_measured.csv` keeps its 5.3b values until the next `infer_block_lengths.py --apply` (owner's call).
- `analyze.py` (788 of 800 lines) and the mimic (782) need a split before they grow.
- Small review notes left in each PR's review comment.

## Wave 3 (2026-11-26)

The owner started a third round from the wave 2 report card, one PR per lane:

| Lane | Scope |
|---|---|
| L1 | Card pipeline: `generate_all_cards`, `generate_card_template`, `engine_lookup`, `card_template_sheet` and `card_template_waybill`; `build_card` and `build_waybill_card` as steps over typed records; the IMG_9088 case in data; no exits at import |
| L2 | Station maps and publications: the three renderers on `station_compass.py` with behaviour tests; `rebuild_dispatcher_train_list`, `rebuild_yardmaster_sequence`, `rebuild_local_station_maps` |
| L3 | Site share cards: `share_card_recipes/composites.py` and `forms.py` |
| L4 | `render_cats_panel.py`, `cs105_consist.py`, `export_track_lengths.py` |
| L5 | Garbled docstrings, source-text host tests, the film frame loop into `film_common` |
| L4b | Card generators, after L4 and L5: `cars.py` split under the size limit; `generate_cc_waybill_labels`, `generate_waybill_cards` and `generate_single_card` on the shared sticker deck writer and typed records |
| L6 | Types, after L1 to L5 and L4b: `build_device_map` and `build_cats_panel` typed to B+ |
| L7 | Exemplary core, after L6 (owner): `build_device_map.py`, `build_cats_panel.py` and `device_map_records.py` to A or better, as examples of the repo's best code; outputs and panels unchanged |
| L8 | Data-in-code check (owner): a `tools/audit/` check beside `check_data_readers.py` that fails when railroad data is typed into code, with a CSV allow list read through hartlib and a baseline of the 131 Python tables and the JS tables |
| L9 | Fixes from the regrade: the stale spurs path in `generate_operator_sheet`, an empty party pool in `waybill_sheet` as a named error, `waybill_deck` and `intake_stages` on typed records |
| L10 | A light PR kind (owner): `tools/ci/changed_kind.py` and `light_checks.sh`, so a docs-plus-map-preset change skips the full remote run by tool, not by waiver |
| L11 | Showcase follow-up (owner): the `MastPlan` cast in `build_device_map`, the `bindings()` guard in `build_cats_panel`, `device_map_nodes` typed |

Moved to a later wave (owner):
- The device-row callers that still read by key, and `tools/ops` to mypy strict (L6 part 2). L7 updates only the callers it breaks.
- The owner tags and dates inside the `NOT_WIRED`, `HEAD_NOT_WIRED` and `_control_points` strings of `build_device_map.py`: they are written into the outputs, so removing them changes `devices_generated.csv` and `plan_generated.json`.
- Narrow the folder-wide unit and portal declarations (www/, docs/, ops/, wiki/) so more data edits count as light (owner, 2026-11-26). Today the light kind means docs plus the map presets.
- The coordinate skill calls Markdown under `.claude/skills/` docs-only, but `tools/ci/changed_kind.py` treats everything under `.claude/` as full, on main too.
- `repo_guide_page.py` treats any argument other than `--check` as a write run.
- `skip_or_fail` is copied in five `tools/schematic` tests; make it one shared helper.
- From L11: `level_signals()` in `build_cats_panel.generate()` is still outside the `SchematicError` guard, and `device_map_inputs.read_pins` and `frozen_wires` are loosely typed.
- From the L9 review: the `sheet_kit` SystemExit, the unused `_chrome`, the `test_cars_sync` temp folders and the `test_package_contents` check of the retired `archive/` folder.
- From the L11 and L10 reviews: the `panels.toml` device-map description, the `device_map_masts` mast-name copy, `MastEntry` as `dict[str, Any]`, and the private imports and bare-tuple records in `changed_kind.py`.
- Unverified review notes on main, to check before fixing:
  - `apply_hart_package_local.ps1` near line 346 trusts a stale `jmri_profile_id.txt`, because the resolver reuses its output file without `-Force`.
  - The Pi `apply_hart_package_local.sh` near line 180 finds the JMRI process with a prefix pattern, so `TCS_MQTT_test` would match `TCS_MQTT`.
  - The `jmri_profile.py` backup stamp has one-second resolution, so two runs in a second overwrite each other, and its `insert_after` and `remove_script` tests match a substring.
  - In `check.yml` the schematic cache warm-up is gated on `kind != 'docs'`, so a light PR still runs it on a cache miss (12 to 34 minutes).
  - `light_checks.sh` is committed 100644 while `docs_checks.sh` is 100755, and `changed_kind.map_display_only` never checks that the presets differ.
  - Checked and closed: `intake_stages.py` near line 271 dropped SystemExit from the per-photo guard, and nothing it calls raises SystemExit.
- Site pages that may be stale, not confirmed: the repository guide (docs-only and light paths), and `jmri-additions` and `tables-file` (the deploy sets saved panel window sizes).

PRs: L3 #1261, L2 #1262, L1 #1264, L4 #1265, L5 #1266, L4b #1267 and #1268, L6 #1269, L7 #1272, L9 #1273, L8 #1274, L10 #1277, L11 #1278. Only #1265 shipped from the lanes, to the site. The other deploys that ran during the wave were for #1271 (Pi and Windows, by the main session), #1274 and #1275 (site), each with every Build count unchanged.

Report card after wave 3 (https://claude.ai/artifact/2feCxg41LpAFfoP3e6Z8nE): the line-weighted average went from 3.12 to 3.16 (B), over 508 source files and 124,075 lines. C and D files went 16 to 17, none at D. A-range files went 133 to 147, and reviewers have read 488 source files. Fifteen of the 16 C files from wave 2 are now B or better (L1 to L4, L4b), and `generate_operator_sheet` went from F to B+ in L9. A fresh read of files changed since wave 2 put 16 other files at C or C+. The goal of no C files is not met, and B+ (3.3) is 0.14 away; fixing every C file would give about 3.21.

### Left after wave 3

- 17 files at C: `gen_ctc_track_plan.py` (C-, parked by owner ruling, 2026-11-26, not regraded), `rebuild_station_map.py` (C), `sharpen_card_fill_images.py` (C), and C+ for `run-modern.js`, `rebuild_station_map_full.py`, `build_signals.py`, `panel_status_turnouts.py`, `build_masts.py`, `build_hart_signal_heads.py`, `mimic_view.js`, `launch_cats.sh`, `build_hands.py`, `clear_mqtt_cmd_sensor_retain.py`, `page_figures.py`, `sync_mqtt_turnouts_from_fb.py`, `panel_snapshot.py` and `fetch_cats_3.2.sh`. The reasons are on the report card.
- The largest gaps to B+ by lines times points: `rebuild_station_map.py`, `audit_panel_contracts.py`, `store_split.py`, `crop_car_image.py`, `crew.js`, `build_wiring_json.py`, `mast_rule.py`, `staging_device_map.py`.

## Wave 4 (2026-11-27)

| Lane | Scope | PR |
|------|-------|----|
| 4-T1 | Website table moves (session lnevo-5f) | #1284 merged |
| 4-T2 | Road tables (lnevo-5f) | #1289 merged |
| 4-T3 | Industry tables (lnevo-5f) | #1294 merged |
| 4-T4 | Station map tables (lnevo-5f) | still open at the end of the wave |
| 4-L1 | `build_signals`, `build_masts`, `mast_rule`, `device_map_masts`: one mast-name source, typed `MastEntry` | #1293 merged |
| 4-L2 | `build_cats_panel` `level_signals` guard, typed `read_pins` and `frozen_wires`, one `skip_or_fail` helper, `staging_device_map`, `build_hands`, `panels.toml` text | #1297 merged |
| 4-L3 | Jython `panel_status_turnouts`, `build_hart_signal_heads`, `audit_panel_contracts`; tools/mqtt `clear_mqtt_cmd_sensor_retain`, `sync_mqtt_turnouts_from_fb` | #1292 merged |
| 4-L4 | `launch_cats.sh` (both), `fetch_cats_3.2.sh`, `panel_snapshot.py`; the three unverified host notes, checked then fixed | #1286 merged |
| 4-L5 | `changed_kind.py` records, the `.claude/skills` Markdown rule with a narrowed `check_stamps.REPO_FILES` (owner), `light_checks.sh` mode, `check.yml` warm-up gate, `repo_guide_page.py` arguments | #1285 merged |
| 4-L6 | `rebuild_station_map` and `_full`, `sheet_kit`, `sharpen_card_fill_images`, `crop_car_image`, `test_cars_sync` and `test_package_contents` | #1288 merged |
| 4-L7 | Site JS: `run-modern.js`, `crew.js`, `page_figures.py` | #1290 merged |
| 4-L7b | `mimic_view.js` DOM rows | #1287 merged |
| 4-L8a | hartlib `store_split` | #1291 merged |
| 4-L8b | `tools/ops` to mypy strict | #1298 merged |
| 4-L9 | Owner tags and dates out of the `build_device_map` output strings (only note text changed in the outputs) | #1299 merged |
| 4-L10 | Narrower unit and portal declarations | #1295 merged |

Other PRs: wave page #1283, sampler `find -L` #1296. Shipped: #1286 to the Pi and Windows; #1287 and #1292 together; #1299; #1284 and #1290 to the site.

### Result

Report card after wave 4 (https://claude.ai/artifact/2feCxg41LpAFfoP3e6Z8nE, "After wave 4"): the line-weighted average went from 3.183 to 3.204 (B), over 517 source files and 125,145 lines. Two files are at C or below: `crop_span.py` (C+) and the parked `gen_ctc_track_plan.py` (C-). A-range files went from 157 to 160, and reviewers have read 497 source files. B+ (3.3) is 0.10 away.

The wave 3 card was wrong. Its merge script applied an older sweep grade over the newer wave 2 reading for every file wave 3 did not change. Corrected, wave 3 is 3.183 with 2 C files, not 3.158 with 17. Several wave 4 lanes worked on files that were already B or better (for example `rebuild_station_map.py`, A- since wave 2).

| | Start | Wave 1 | Wave 2 | Wave 3 (corrected) | Wave 4 |
|---|---|---|---|---|---|
| Average | 2.86 | 3.03 | 3.12 | 3.183 | 3.204 |
| C and D files | 64 | 33 | 16 | 2 | 2 |
| A-range files | 8 | 18 | 133 | 157 | 160 |

### Left after wave 4

- Device rows: about 489 uses of `DeviceRow`'s mapping view in 67 files. Wave 5 removes the view: readers take `DeviceRow` fields, and the writer and check side keeps text rows through a new `DeviceRow.cells()` (option A, chosen by the coordinator; the owner may override). `row["level"]` is text where `.level` is an int, and `row.get("comment")` is None where `.comment` is built.
- `test_name_copies` scans every tracked file, which keeps the unit guards at everything, so no data edit in ops/, docs/ or www/ can be light. Several tests also read masters they do not declare (`test_check_data`, `test_check_hand_tables`, `test_check_locos`, roster and fleet gallery, `test_check_json`, `test_speedmatch_speed_table`).
- `crop_span.py` (C+): `_core_body_span` keeps its thresholds inline.
- Size limits close: `mast_rule.py` 786 of 800, `build_wiring_json.py` 785, `lcos_mqtt_mimic.py` 782.
- Host scripts: no shared whole-word profile match for `pi_start_panelpro`, `pi_quit_panelpro` and `panelpro_session`; `panelpro_restart_due.sh` keeps its own JVM pattern; CATS starts with `--profile`, so the apply step cannot see it before it edits `user-interface.xml`; the Windows retired-entry regex and `insert_after` match substrings; `profile.xml` is not written atomically.
- Small: `check_json` schema nodes as `dict[str, Any]`; `crew_schema` does not require `spotsheet.desk` or per-map tracks; a fixture still carries an owner tag; `test_package_contents` lost the `apply_dispatcher_roster_profiles.py` check; `repo_guide_page.py` keeps bare dicts.
- Unverified: the site pages `behind/tables-file.html` and `library/repository-guide.html` may be stale; each PanelPro quit for a deploy logs a WiThrottle "readLine failure limit exceeded" line; the mimic page has not been loaded in a real browser since #1287; `mosquitto_cli` timeout handling has not run against a live broker.

## Wave 5 (2026-11-27)

The wave 5 coordinator (a background agent of hart-e0) planned these lanes from the wave 4 card and the list above, while the owner was away. Nothing waited on the owner; two choices the owner may override are listed under Result.

| Lane | Scope | PR |
|------|-------|----|
| 5-L1 | Device rows, part 1: `MasterRow.cells()` and `level_cell`; hartlib readers on fields | #1304 merged |
| 5-L1b | Device rows, part 2: callers in www/scripts, tools/audit, jmri and cats tests | #1310 merged |
| 5-L1c | Device rows, part 3: tools/schematic and hartlib tests on fields, then the mapping view removed; public `devices.row_rank`; `ItemKey` and `BeanKey` store keys | #1313 merged |
| 5-L2 | `test_name_copies` rename test on a scratch checkout; the master reads unit tests make declared in `check_stamps.py` | #1309 merged |
| 5-L3 | Card pipeline: `crop_span.py` thresholds named in `CROP`, `_core_body_span` split, typed photo rows | #1303 merged |
| 5-L4 | `mast_rule.py` split into five modules (786 to 287 lines), `block_layer.py` typed, one owner-name rule | #1306 merged |
| 5-L5 | Host scripts: one whole-word JMRI profile check, the CATS `--profile` form, exact Start Up anchors, atomic `profile.xml` | #1305 merged |
| 5-L6 | Site JS: `archive.js`, `gallery.js`, `wiring.js`, `crew.js` split into plain functions; `crew_schema` requires the desk notes and tracks | #1301 merged |
| 5-L7 | Jython: `audit_panel_contracts.py` split (1024 to 548 lines), one SML destination walk, `panel_status` failures printed | #1302 merged |
| 5-L8 | Exam JS: `run.js` and `run-modern.js` share names through `take` and `give`; the answer key reads data, not code | #1311 merged |
| 5-L9 | `build_wiring_json.py` and `lcos_mqtt_mimic.py` split by job | #1308 merged |
| 5-L10 | `check_json` TypedDicts, CLI usage errors, the fixture tag, `panel_status_clicks` and `_turnouts` failures printed | #1307 merged |
| 5-L11 | hartlib `tables_build.py` split into six modules (1186 to 547 lines), `block_layer.py` split | #1312 merged |

Other PR: wave page #1300. Shipped: #1302 (layout 03:54); #1304 and #1307 (04:34); #1305 (05:01); #1308 (05:09); #1310 to #1313 (06:23); #1301 (site 04:00) and #1311 (site 05:37). Every layout deploy passed the Mac PanelPro smoke test and the strict panel audit, and the Pi's log showed no script errors after the restart. Session lnevo-5f's station map tables (4-T4) did not reach the queue during the wave.

### Result

Report card after wave 5 (https://claude.ai/artifact/2feCxg41LpAFfoP3e6Z8nE, "After wave 5"): the line-weighted average went from 3.204 to 3.232 (B), over 539 source files and 126,723 lines. A-range files went from 160 to 181, and reviewers have now read 519 source files. B+ (3.3) is 0.07 away.

| | Start | Wave 1 | Wave 2 | Wave 3 (corrected) | Wave 4 | Wave 5 |
|---|---|---|---|---|---|---|
| Average | 2.86 | 3.03 | 3.12 | 3.183 | 3.204 | 3.232 |
| C and D files | 64 | 33 | 16 | 2 | 2 | 3 |
| A-range files | 8 | 18 | 133 | 157 | 160 | 181 |

Three files are at C or below: the parked `gen_ctc_track_plan.py` (C-); `www/js/archive.js` (C+, down from B-: its mount is one 263-line closure, and its lightbox and view code copy `gallery.js`); and `tools/schematic/cats_panel_facts.py` (C+, down from B on a closer read: 14 bare fields built by position). `crop_span.py` went from C+ to B+ and `mast_rule.py` from B- to A-.

Coordinator choices the owner may override:
- Device rows option A: readers take `DeviceRow` fields, and writers and checks take text rows through `cells()`. The mapping view is now gone.
- 5-L2 raised the `check_stamps.py` EXTRA row in `tools/audit/hand_tables.csv` from 36 to 46 entries and added keep rows for `ENTITY_MASTERS` and `SIDECAR_MASTERS`, because they are stamp declarations, not railroad data.

Checked and closed: the repository guide and tables file pages are current by their own checks; the mimic page loads in a browser from the Pi with every level, turnout and sensor shown and no page errors.

### Left after wave 5

- `archive.js` (C+) and `gallery.js` share the view bar, toast and lightbox code; sharing it needs `nav.js` or a new file. `crew.js` (740 lines) and `archive.js` stay one file each so the pages' script tags do not change. `crew_schema` does not require `spotsheet.offline`.
- `cats_panel_facts.py` (C+): typed `Facts`, annotations, the unused `F` parameter, a dated comment.
- `tables_build.py` keeps about 25 re-exported names for the device-row files; repoint those callers and drop the block. `refuse_generated` and `check_layout_facts.py:396` still raise SystemExit outside main; `tables_page.PageError` subclasses SystemExit.
- Swallowed errors in `sml_beans.py` (183, 340, 348) and `sml_ui.py:102`; `test_turnout_startup.py:85` turns any solver bug into a skip.
- `apply_hart_package_local.sh` (104-124) keeps its own copy of the Jython script list from `common.sh`, with no test that they match.
- Only `run-modern.js` uses `take` and `give`; `run-1949.js`, `run-signals.js` and `run-yard.js` still read `ExtraEast` directly, and the answer key still reads `renderSheet` with a regex.
- `ops/` and `www/data/` edits stay full, because the unit declarations still cover those whole folders.
- The mimic shows the broker as connected as soon as `mosquitto_sub` starts; its POST handler answers 400 before 404 for an unknown path.
- Dated history in some tests (`test_block_layer.py`, `test_blocks_every_level.py`, `test_masts_every_level.py`, `test_live_desk_levels.py:63`) and in `lcc_turnout_contract.py:9`.
- The top gaps to B+ after `archive.js`: `device_map_staging.py`, `gallery.js`, `build_exam_answers.js`, `hart_pub_helpers.py`, `rebuild_scale_operating_instructions.py`, `check_layout_facts.py`, `levels_page.py`, `le_names.py`.
- Not checked: the WiThrottle "readLine failure limit exceeded" line comes every 5 minutes from a client that opens port 12090 and closes; it is not tied to PanelPro quits, and nothing on the Pi starts it.

## Wave 6 (2026-11-27)

The wave 6 coordinator (a background agent of hart-e0) planned these lanes from the wave 5 card and the list above. Lanes 6-L1 to 6-L7 start first; 6-L8 to 6-L14 start as those finish.

| Lane | Scope | PR |
|------|-------|----|
| 6-L1 | Site viewer: `archive.js` and `gallery.js` share one lightbox, view bar and toast module; the archive mount split into functions | |
| 6-L2 | CATS panel: typed `Facts` in `cats_panel_facts.py`, annotations, the unused `F` parameter; `cats_panel.py`, `cats_panel_dress.py` | |
| 6-L3 | `tables_build.py` re-exports dropped and callers repointed; `refuse_generated` and `tables_page.PageError` off SystemExit; `test_turnout_startup` skip narrowed; hartlib README | |
| 6-L4 | `check_layout_facts.py` split by job, SystemExit at 396 | |
| 6-L5 | Jython: swallowed errors in `sml_beans.py` and `sml_ui.py`; the setAppearance failure printed once per message; `lcc_turnout_contract.py` | |
| 6-L6 | Host scripts: one Jython list for `apply_hart_package_local.sh` and `common.sh`; the audit's stored counts from one source | |
| 6-L7 | Exam JS: `run-1949.js`, `run-signals.js`, `run-yard.js` on `take` and `give`; the answer key reads data; `build_cats_layout_index.py` | |
| 6-L8 | `device_map_staging.py` and `staging_device_map.py` | |
| 6-L9 | `le_names.py`, `le_tables.py`, `render_le_layout.py` (800 of 800 lines) | |
| 6-L10 | Ops publications: `hart_pub_helpers.py`, `rebuild_scale_operating_instructions.py`, `rebuild_crew_instructions.py` | |
| 6-L11 | `levels_page.py`, speed-match `make_job.py`, `freeze_wiring.py` | |
| 6-L12 | Mimic: the broker shown connected only after `mosquitto_sub` proves itself; POST 404 before 400; `build_mimic_web` error | |
| 6-L13 | `device_map_rows.py`, `device_map_masts.py`; dated history in the block and mast tests | |
| 6-L14 | Test selection: unit declarations for `ops/` and `www/data/` narrowed to what each check reads | |
