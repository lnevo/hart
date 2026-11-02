# Prompt: build the HART Operations Pro database

Give this to a Claude Code session that has the `operations-pro` plugin loaded (`external/model-railroad-skills/plugins/operations-pro`). Paste everything under the line.

Before using it, confirm the plugin loads (`ops_actions` lists the actions) and that PanelPro is closed on the host that owns the Operations folder.

---

## Task

Build the HART Operations Pro database for the Neville Island operation, so that Operations Pro produces the same kind of operating session the STS build produces today. Work on a **copy** of the Operations folder first. Do not touch the live Pi or Windows data.

The aim is the same railroad, expressed the Operations Pro way. It is not a transliteration of the STS tables. Where STS and Operations Pro model something differently, say so, choose the Operations Pro idiom, and record the choice.

## How to work

1. Read the plugin skill first (`skills/operations-pro/SKILL.md` and its references), then the sources below.
2. Do not guess. When a fact is missing, list it as an open question, ask me, and carry on with the parts that do not depend on it.
3. Build in the order the program needs: car types, roads, loads, locations and tracks, industries and their schedules, routes, trains, train schedule days, cars, locomotives, then automations and manifest format.
4. Every change goes through `ops_plan`, then `ops_apply` after I have seen the diff. JMRI stays exited for file changes.
5. After each stage run `ops_audit`. Before the end run `ops_dry_run` and `ops_build_check`. Report each train's outcome.
6. Keep a running decision log in the repo (see Deliverables).

## Sources (read these, in this order)

**What STS builds today (the model to match)**

- `external/sts-helpers/seed/hart_seed_config.json`: stations, jobs (D749, NVL, CK1, STG-SCULLY, STG-DEMMLER), pickup criteria, session operations, car home yards, coke lanes, offline stations, traffic multipliers, shipment code overrides.
- `external/sts-helpers/docs/HART_STS_REQUIREMENTS.md`: job step rules, one destination per pickup step, coke shipments and locations.
- `external/sts-helpers/docs/FULL_OPERATING_SESSION.md`, `BEGIN_SESSION_STEPS.md`, `WARM_START_STEPS.md`, `SWITCHLIST_BUILDING.md`: the session cycle and how switch lists are phased.
- `external/sts-helpers/seed/inputs/`: `HART_Spot_Waybills.csv`, `spot_assignments.csv`, the three `*_shipping_map_proposed.csv` files, `spurs/`, `HART_MergedCarRoster.xml`.
- The STS session editor pages in `external/sts-docker/sts/` (`db_edit_locations.php`, `db_edit_jobs.php`, `db_edit_shipments.php`, `db_edit_routing.php`, `db_edit_car_codes.php`, `db_edit_commodities.php`, `db_edit_special_pool.php`, `db_edit_empty_locations.php`): the fields the owner actually edits between sessions. Anything the owner edits there is a candidate for something the Operations Pro data must also let them edit.

**The operation as it is run**

- `docs/ops/`: Scale Operating Instructions, Dispatcher Train List, Yardmaster Sequence, the three Crew Instructions (D749, NVL, CK1), the New Operator Primer, the station maps. These say what crews are told to do, in the owner's words.
- `ops/car-cards/data/OperationsCarRoster.xml` and `OperationsEngineRoster.xml`: the existing Operations Pro rosters. Per ADR-013 these are fed from the car repository (`bin/cars`). **Add cars; never replace the roster**, so session state survives.
- `wiki/decisions/ADR-013-car-repository.md`, `ADR-005-public-equipment-names.md`, and `jmri/layouts/hart/data/public_name_map.csv`.

**The physical model (what building and running it has taught us)**

- `jmri/layouts/hart/data/block_lengths.csv`: real track lengths in inches. Use these for Operations track lengths (convert to the Operations length unit and say which you chose), not STS spot counts.
- `docs/ops/Neville_Island_Station_Map*.docx` and the birdseye image: where the tracks are.
- `wiki/STATUS.md`: current railroad state.

## Mapping to establish

Produce a table first, before writing any data, showing how each STS concept maps. Start from this and correct it:

| STS | Operations Pro | Question to settle |
|---|---|---|
| Station (North Yard, West Yard, East Yard, South Yard, Scully Yard, Demmler Yard, Neville Island, Shenango Coke Works, Mckeesport-PA, McKees Rocks-PA) | Location (and Division if useful) | Which are real locations and which are offline party tracks? |
| Location code and track/spot | Track under a location | How many spots become track length, and which become separate tracks? |
| Interchange yards Scully (POHC) and Demmler (CSX) | Interchange tracks, with owner restrictions | Who may deliver to and pick up from each? |
| Offline party tracks (McKees Rocks, Mckeesport) | Staging or interchange tracks | Staging is destructive on terminate; which fits the "swap offline and online" STG jobs? |
| Job (D749, NVL, CK1) | Train and Route | One route per job, with the stops from the Crew Instructions |
| STG-SCULLY, STG-DEMMLER | Train terminating into and building from staging | Do these need to be trains at all? |
| `pu_criteria` (step, destination station) | Route location pick up and set out rules, car type and road/load restrictions, destination restrictions | Operations Pro has no per-step destination filter; what replaces it? |
| Shipment code and waybill | Industry schedule (custom loads in and out) plus a car's final destination | One schedule per industry with the commodities from `HART_Spot_Waybills.csv` |
| Car code (XM, HM, HC, TA, and so on) | Car type, plus load | Align with the types already in the Operations roster |
| Traffic multipliers, shipment yard balance | Schedule counts, move counts, and traffic balance settings | How is relative traffic expressed? |
| Warm start | Dry-run sessions on a copy, then Restore of the result | Is a warm start still wanted? |
| Begin session | An automation | See below |
| Session number and "play session" | Train schedule day and an automation | See below |

## Session design

STS opens a session, auto-assigns, and the jobs run in an order the crews know. Express that in Operations Pro with an **automation** (or a small set of them), and a **train schedule day per session type** if more than one pattern is needed.

Settle and record:

1. The build order: D749 first, NVL after D749 clears the bridge, CK1 on its own, then the staging trains at session end. Operations Pro builds in the order the automation lists; on-time build mode forces departure order, so say whether to use it.
2. The terminate order. Trains do not finish in the order they were built (D749 terminates last at West Yard, after NVL and CK1). Confirm in a dry run that terminating a later-built train first leaves the earlier train's cars intact, and that cars a terminating train frees are available only to trains built after it.
3. Groups. Which trains are built and terminated together so later groups can draw on freed cars. Use wait-for-terminate steps.
4. Days. An automation can set a named day but cannot step to the next one. Decide whether HART needs more than one day, and if so make one automation per day or a master automation that runs them.
5. No message or Yes/No step unless it is intended, since it opens a modal window on the JMRI computer and stops an unattended run.

## Constraints

- **Names.** HART's expansion is private. Do not spell it out in any file, comment or report. Keep **P&CV** and **P&OV** distinct and never normalise one to the other. Use the public equipment names from ADR-005 for anything a visitor could see.
- **Staging at Scully and Demmler** is a modelling choice, not a fact. Present the options and their consequences before choosing.
- **Do not** use anything that moves turnouts or publishes `track/cmd`. This job touches only the Operations folder.
- **Do not** patch JMRI or the plugin. If the plugin cannot express something, stop and report the gap.
- **Do not** start PanelPro or CATS, and do not leave any bridge running.
- **Do not** store anything into `jmri/layouts/hart/output/tables.xml`.
- Cars: add from the repository; do not overwrite existing car state. Cars with no photo are still cars for Operations Pro, but record which they are, since STS leaves them out.

## Deliverables

1. `docs/ops/OPSPRO_MAPPING.md`: the mapping table, completed, with each choice and its reason.
2. The built Operations folder on a copy, with the path reported.
3. `docs/ops/OPSPRO_OPEN_QUESTIONS.md`: what you could not decide and what you need from the owner.
4. A dry-run report: each train, its outcome, cars moved, cars refused and why, and the audit findings that remain.
5. A list of every place Operations Pro cannot reproduce the STS behaviour, and the nearest substitute.
6. A proposed way to keep the cars (ADR-013) and the Operations folder in step.

Stop after the mapping table and ask me to approve it before building anything.
