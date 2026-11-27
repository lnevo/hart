# Code-quality wave (2026-11-26)

Status: active (wave 3, from 2026-11-26 19:10)
Coordinator: hart-bb, since 2026-11-26 14:15 (holds the merge queue and the deploys; a background coordinator runs the lanes)
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

Moved to a later wave (owner):
- The device-row callers that still read by key, and `tools/ops` to mypy strict (L6 part 2). L7 updates only the callers it breaks.
- The owner tags and dates inside the `NOT_WIRED`, `HEAD_NOT_WIRED` and `_control_points` strings of `build_device_map.py`: they are written into the outputs, so removing them changes `devices_generated.csv` and `plan_generated.json`.

