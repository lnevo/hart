# Code-quality wave (2026-11-26)

Status: active (wave 2, from 2026-11-26 14:15)
Coordinator: hart-bb, since 2026-11-26 14:15 (holds the merge queue and the deploys; a background wave 2 coordinator runs the lanes)

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

## Left

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
