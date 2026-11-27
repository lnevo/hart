# Data masters: phase 1 lanes (2026-11-25)

Status: active

Plan for [ADR-039](../decisions/ADR-039-data-masters-in-git.md): one master per kind of record in git, column sidecars checked by `check.sh`, stable keys, and no spreadsheet as an input. Phase 1's lanes L8 to L15 merged on 2026-11-26 and are deployed to the Pi, Windows and the site (a1b762ca); L7 was done on 2026-11-25 (#1173). Phase 2 (drift reports against STS, Operations Pro and JMRI, the SQLite view, and a database if one is ever needed) starts once phase 1 is done.

## Lanes

| Lane | Job | Owns | Starts after | Agent, review |
|---|---|---|---|---|
| L1 Catalogue | `docs/data/entities.csv` and its README: each kind of record, key, master, copies, outside tools, which side wins in a session. Masters chosen by the owner on 2026-11-25 (in `docs/data/README.md`). **Done** in the L1 PR. | `docs/data/` | this page | `repo-auditor` drafts, main session writes; no review (docs) |
| L2 Validator | `tools/ops/check_data.py`, the extended sidecar format, sidecars for `devices` and `switches` converted; the ADR-037 session adds the `data-schemas` step after its stage 4b **Done** 2026-11-25 (#1146): `data-schemas` step, format in `docs/data/sidecars.md`. | `tools/ops/check_data.py`, `*.columns.csv` format | L1 | `general-purpose`, opus; `/code-review medium` |
| L3 Wiring inputs | `build_wiring_json.py` and `create_wiring_schematic_ppt.py` read `hartlib.wiring`, not v86 (the signal split and v85 were archived on 2026-11-25) **Done** 2026-11-25 (#1145): v86 is an output only. | `www/scripts/build_wiring_json.py`, `tools/wiring/`, `docs/wiring/` | L1 | `general-purpose`, opus; `/code-review high` (`hartlib` reader) |
| L4a Industries | new master `ops/hart-ops/data/industries.csv`; `industry_id` and spot keys across `spot_assignments.csv`, `HART_Spot_Waybills.csv`, `industries.json`; sidecars **Done** 2026-11-25 (#1155). | `ops/hart-ops/data/`, `www/data/industries.json` and its readers | L2 | `general-purpose`, opus; `/code-review medium` |
| L4b Trains | new master `ops/hart-ops/data/trains.csv` keyed on train symbol; `cats/data/hart_trains.csv` built from it and recorded in the pipeline map; `crew.json` jobs checked against it; sidecar **Done** 2026-11-25 (#1156). | `ops/hart-ops/data/trains.csv`, `cats/data/hart_trains.csv`, `www/data/crew.json` readers | L2 | `general-purpose`; `/code-review medium` |
| L4c Places | one id for station and for control point across `stations.csv`, `interlockings.csv` and the devices' `cp`; block `id` in `occupancy_bindings.csv`; sidecars **Done** 2026-11-25 (#1181). | `jmri/layouts/hart/data/schematic/`, `cats/data/occupancy_bindings.csv`, the CATS builders | L2, and no open schematic or naming PR on the same files | `schematic-builder`; `/code-review high` |
| L4d Locos | `roster_id` as key in `locos.csv`, `new_locos.json` built from it; sidecar **Done** 2026-11-25 (#1154). | `ops/hart-ops/data/locos.csv`, `bin/cars locos` | L2 | `general-purpose`; `/code-review medium` |
| L5 Crew and industry text | one record source for crew colors, jobs and their text: a new JSON master under `ops/hart-ops/data/`, with industry blurbs in `industries.csv` (`blurb`, added by L4a). `www/data/crew.json` and the `rebuild_*.py` docx are generated from them; crew.json's hand-copy note goes. L4b's train-symbol check is repointed at the new master **Done** 2026-11-25 (#1166). | `ops/hart-ops/publications/`, the new crew master, `www/data/crew.json` | L4a and L4b | `general-purpose`, opus; `/code-review medium` |
| L6 Fleet and archive | `www/data/fleet-gallery.json` becomes a checked copy of the car and loco masters; the archive stays one catalogue of items (id, credit, file path), `www/data/archive.json` is checked against it, and the lineage pages cite those ids. No database **Done** 2026-11-25 (#1165). | `www/data/fleet-gallery.json`, `www/data/archive.json`, the catalogue, `www/js/lineage.js` and the lineage pages | L4d | `general-purpose`, opus; `/code-review medium` |
| L7 Roster typo ids | apply the ten `ROSTER_TYPO_IDS` renames once, in the car master (`image_metadata.csv`) and in the live STS (the Mac copy first, the owner approves, then the Pi: `sts-live` skill), then delete the map from `build_merged_car_roster.py` and `cars.py`. The seed session rules stay as session rules | `ops/hart-ops/card_pipeline/`, `ops/hart-ops/data/image_metadata.csv` | the owner's yes on the Mac STS | **Done** 2026-11-25 (#1173), no STS write needed |
| L8 Block lengths | plan lengths from AnyRail only, speed-matching lengths as an override file; hartlib gives a plan and an operating length, each reader on one side ([rule](#block-lengths-l8)) **Done** 2026-11-25 (#1191). | `jmri/layouts/hart/data/block_lengths*.csv`, `tools/schematic/plan_lengths.py`, `jmri/layouts/hart/scripts/infer_block_lengths.py`, the hartlib length readers | L4c | `schematic-builder`; `/code-review high`; PanelPro test and a layout deploy |
| L9 Switch facts | staging rows of `switches.csv` lose the `os_block`, `closed_leg` and `thrown_leg` label copies (hartlib resolves them from the ids); `build_hands.py` writes hands only; `area` refers to `schematic/lcos_nodes.csv` `area`; the switch lists in `stations.csv` and `interlockings.csv` keep one direction of the switch-to-control-point link **Done** 2026-11-25 (#1192). | `switches.csv` and its sidecar, `build_hands.py`, the hartlib switch reader | L8 | `schematic-builder`; `/code-review high`; `make panels CHECK=1` unchanged |
| L10 Orphans | archive `industries.txt`, `www/data/panels.json`, `www/library/updated-history.txt` and `cats/panels/reference_ArmstrongMagnet.xml`; give `invites.json` and the waybill inventory catalogue rows **Done** 2026-11-25 (#1188). | those files | this page | `general-purpose`; `/code-review medium` |
| L11 Hand lists | catalogue rows for 14 hand-kept lists, sidecars for the schematic override lists and the two `lcos_signal_*.csv`, schema checks for `plan_overrides.json`, `preferences.json`, `panel_items.json` and `published-files.json` **Done** 2026-11-25 (#1197). | their sidecars and schema checks | L4c | `general-purpose`; `/code-review medium` |
| L12 Frozen copies | delete `baselines/` and its capture script; one `speed_by_step` copy; `cats_discipline` becomes a `devices_field.csv` column and `occupancy_bindings.csv` retires (owner's choice) **Done** 2026-11-26 (#1204). | `baselines/`, the speed-step copies, `occupancy_bindings.csv` and its readers | L8 and L9 | `schematic-builder`; `/code-review high`; layout deploy |
| L13 Site data, one writer | `map_revision` stops patching `www/data/crew.json` and rebuilds it through `crew_master`; the `www/scripts/map_revision.py` wrapper goes **Done** 2026-11-25 (#1187). | `hartlib/map_revision.py`, `www/scripts/map_revision.py` | this page | `/code-review high` |
| L14 Panels order | check whether `main-route` reads `device-map`'s control points and stations; declare it in `panels.toml` or comment why not **Done** 2026-11-25 (#1185). | `tools/pipeline/panels.toml` (with the ADR-037 session) | this page | small |
| L15 Turnout control points | a turnout row in `devices_field.csv` no longer holds `cp`: `hartlib.places.switch_place` gives it from `stations.csv` and `interlockings.csv`, and `devices.check_rows` stops on a turnout `cp` **Done** 2026-11-26 (#1206). | the turnout `cp` cells, `hartlib.places`, the device-map readers | L12 | `schematic-builder`; `/code-review high`; layout deploy |
L4c is the riskiest: it renames references that the panels and the CATS desks read. It runs last of the L4 lanes, with `make panels CHECK=1` and `make panelpro-test` before it merges.

## Block lengths (L8)

The owner's rule (2026-11-25): a block length has two sources. `plan_in` comes only from the AnyRail plan, written by `plan_lengths.py` into a generated file. Speed-matching measurements are an override file (block `id`, `measured_in`, run, date), written only by speed matching, the way the device and wiring overrides sit over their generated files.

- hartlib gives two answers: the plan length, and the operating length (measured where there is one, else plan).
- Speed matching and the Dispatcher's block lengths in `tables.xml` take the operating length. Today `tables.xml` uses `plan_in` for every block, so the 21 timed blocks change.
- Industry spots, the schematic, signal and mast placement, the levels and layout docs and the track-length exports take the plan length only. A check fails a reader on the wrong side.
- `user_name` and `occupancy_sensor` leave the lengths files; the devices hold block identity.

## Rules for the lanes

- The coordinator deploys the site, one deploy at a time (ADR-040). The hold that waited for L5 ended on 2026-11-25 with the deploy of 9ed2cc7a.

- A lane edits only the files in its row. A file that two lanes need goes to the earlier lane, and the later one rebases.
- No lane edits `tools/pipeline/checks.toml`, `tools/check.sh` or `check_stamps.py`: they belong to the ADR-037 session, which adds the `data-schemas` step. Later lanes add sidecar files; the step finds them.
- One merge at a time across sessions. The main session sends "ready #N" to the cleanup coordinator and merges only on "go #N": merge `origin/main` into the branch, push, wait for the required check on that head, merge, and repeat if `main` moved. No auto-merge.
- `wiki/STATUS.md` is frozen while the ADR-038 migration PR is open; after it lands, STATUS lines go in `wiki/status/` entry files.
- At most three lane agents at once, and fewer when the Mac's 8-session cap would be passed (count with `ListAgents` first).
- Lane agents leave this page, ADR-039 and `wiki/STATUS.md` alone and write their status lines to `.claude/progress/data-masters-<lane>.md`. The main session relays them and updates this table after each merge.
- Each lane opens its own PR from its own worktree. Full checks run only through `make remote`.

## Open for the owner

- Lanes L9 to L14 come from a data-cleanup audit the owner approved on 2026-11-25 (session data-cleanup-lanes-l9-l14). Owner's answers on 2026-11-25: loco ids are road name plus road number, formatted for each system; 2091 is POHC; the live Operations Pro roster wins over the snapshot; Route 23 runs 4678; industry `name` takes the Operations Pro spelling (the spot and waybill name columns follow with sts-helpers); Interchange is a kind of traffic, not an industry; the waybill generator stays as it is (STS holds live waybills and the print queue); D749 says "toward McKeesport" and CK1's engine is "Assigned by Yardmaster"; Operations Pro keeps "D749 Return", mapped to D749R; the gallery keeps one photo of PRR 371604, as PRR.
- The 2026-11-25 open questions (L2's spare `detector` cells and `switches.csv` `area`, L4b's staging trains, L4d's locos and DCC addresses, and the rest of that list) were all answered and applied in #1196 on 2026-11-26.
- Left from the reviews, now lane N1 of [night-plunge](night-plunge-handoff.md): `places.table()` and `names()` still read the repo's own lists even for a copied master (L15 fixed `switch_places` only); `places.py` name uniqueness per level; `FactsError` against `DevicesError`; `railroad_facts` `station_group_rows` naming of `cp_id`; a stricter turnout id check in `devices.check_rows`.
- Owner's answers on 2026-11-26 (about 02:45, in session hart-95):
  1. Colour key: full names everywhere ("Demmler Yard; McKeesport", "Scully Yard; McKees Rocks"); the docx `key_label` overrides go. Lane N7 of [night-plunge](night-plunge-handoff.md).
  2. TT-23: the site wording everywhere; the docx subtitle and note overrides go. Lane N7.
  3. YM-01: the NONE row ("No card color", "Yard storage") shows on the site legend too. Lane N7.
  4. The DecoderPro roster becomes a repo master, like the cars and locos. Done in lane N8 of [night-plunge](night-plunge-handoff.md) (#1220, 2026-11-26; [ADR-039 amendment](../decisions/ADR-039-data-masters-in-git.md#amendment-2026-11-26-the-decoderpro-roster-is-a-master-lane-n8)).
