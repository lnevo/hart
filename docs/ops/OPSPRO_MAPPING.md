# HART Operations Pro: mapping and build plan

Stage 1 output of [`OPSPRO_BUILD_PROMPT.md`](OPSPRO_BUILD_PROMPT.md), written 2026-11-02 from the STS session 3 end state (`hart_session_post3_locked`), the seed config, the crew documents, the station maps and the car repository. Stages 2 to 5 build from this file and the three CSVs in [`opspro-build/`](opspro-build/) alone. Decisions the owner may want to reverse are numbered D1 to D30 and listed again in [`OPSPRO_OPEN_QUESTIONS.md`](OPSPRO_OPEN_QUESTIONS.md).

The railroad is the same one STS runs: D749 brings the CSX block from Demmler to South Yard and takes the CSX-bound block away; NVL brings the POHC block from Scully, swaps at South Yard, works the island industries and returns to Scully; CK1 pulls coke from Shenango and sorts it at South Yard; the interchange yards swap with the offline world between sessions. Here that is expressed the Operations Pro way: custom loads and schedules carry the shipments, the router carries a car across trains, and two virtual trains do the offline swap.

## 1. The mapping table

| STS | Operations Pro | Decision |
|---|---|---|
| Station South Yard (8) | Location **South Yard**: yard tracks S-R, S-1, S-2, S-3, S-4; yard track Scale; engine tracks EH-1, EH-2, EH-3 | Real location, measured lengths. The scale is a yard track with a high move count so the builder uses it last (D1). The engine terminal (ET-1..3 on the station map, plates EH-1..3) is three Diesel-only yard tracks at South Yard (D2) |
| Station West Yard (2) | Location **West Yard**: yard tracks W-1, W-2 | Real. Where D749 starts and ties down |
| Station Neville Island (3), one STS location per spot group | Six locations, one per industry, with one spur per spot group and an Off Spot spur as the alternate | The crew documents and the Route 23 timetable name the industries as stations, and colour blocks are per industry (D3). Spots become track length (D4) |
| Station Shenango Coke Works (12) | Location **Shenango Coke Works**: spurs K-1 and K-2 sharing one schedule | The Shenango station map puts the plant on the Princess stubs K-1 and K-2 |
| Scully Yard (9), Demmler Yard (10) | Locations **Scully Yard** and **Demmler Yard**, one **interchange** track each | The loop halves (Track McKees Rocks, Track McKeesport). Interchange, not staging: see section 2 (D5) |
| McKees Rocks-PA (15), Mckeesport-PA (14): the offline party tracks | Locations **McKees Rocks** and **McKeesport**, one **spur** each (POHC Offline, CSX Offline) carrying a mirror schedule | The 46 party codes collapse to one spur per side; the schedule lines are the parties (D6). Spur, not staging: section 2 |
| North Yard (11), East Yard (13) | Not built | Neither holds a car in the STS end state, neither has a measured track, and STS marks East Yard "reserved for future staging" (D7) |
| Job D749 | Train **D749**, route Demmler Yard → West Yard (no work) → South Yard → Demmler Yard | One train, one manifest. On paper it departs Demmler with the block that physically slept in West Yard, as STS's D749 job does (steps at South Yard, then Demmler). D8 was revised after the ordered test: a West Yard terminal cost every Demmler inbound two extra sessions and parked default empties in West Yard |
| Job NVL | Train **NVL**, route Scully Yard → South Yard → Aristech Plastics → Ferrellgas → A. Stucki Co. → Kosmos Cement → Calgon Carbon → Shenango Coke Works → South Yard → Scully Yard | Island order is the East End ladder order from the station map |
| Job CK1 | Train **CK1**, route South Yard → Shenango Coke Works → South Yard | North Yard dropped (D7). K-1 and K-2 are pulled by CK1 only (D9) |
| STG-SCULLY, STG-DEMMLER | Trains **STG-SCULLY** (Scully Yard → McKees Rocks → Scully Yard) and **STG-DEMMLER** (Demmler Yard → McKeesport → Demmler Yard) | They stay trains, run by the automation at session end, with no engine; nobody crews them (D10) |
| `pu_criteria` (step, destination station) | Nothing per step. The router decides which train carries a car from the car's final destination; interchange tracks name the trains that may set out and pull | Operations Pro has no per-stop destination filter. The nearest substitute is the pick up and set out lists on the two interchanges plus car routing via yards (D11) |
| Shipment code | A schedule line: inbound shipments are lines on the offline spur that ship the load to the industry track; outbound shipments are lines on the industry spur that ship the load to the offline spur | `opspro-build/offline_schedule_lines.csv` and `island_schedule_lines.csv` carry the STS code on every line (D12) |
| Waybill, consignment | The load name, plus the line's destination | Commodity names become load names; the chemicals keep their real names and hazmat flag (D13) |
| Car code (XM, HM, HC, TA, FM, FC, GA, RM) | Car type: Boxcar, Hopper or Coke Hopper, Covered Hopper, Tank, Flatcar, Coilcar, Gondola, Reefer | The STS code wins over the repository's `car_type`, which lumps covered and open hoppers. The 16 coke-fleet cars get their own type so coal and coke do not mix (D14) |
| Traffic multipliers, interval and amount, yard balance | Schedule line `random` and `count`, route stop moves, track move counts | Rare IX lines carry random 50; island lines carry none. Balance is re-tuned after dry runs, not copied from STS (D15) |
| Outbound empty return (`outbound_empty_return`) | The industry line's destination: Aristech and Calgon empties go to McKees Rocks, the rest to McKeesport | Kept as STS has it (D16) |
| Car home yard | Not used. No divisions | Divisions would duplicate what the line destinations already say (D17) |
| Warm start | Not reproduced. The start state is the STS session 3 end state, cars placed as `car_start_positions.csv` says | A dry run on a copy is the test; no warm-start replay (D18) |
| Begin session, play session | One automation, **Session**, with wait steps; a second, **Session Replay**, that moves and terminates for unattended tests | Section 7 (D19) |
| Session number | None. No train schedule days are used; the active day stays unset | One session pattern, so no day is needed (D20) |
| Unavailable cars | `out_of_service` | From the repository, as ADR-015 already does |
| Track scale (weigh, reload) | Not expressible. CK1 sets coke out at South Yard and the yardmaster weighs by hand; off-tolerance reloads are a Set Car back to Shenango | Deliverable 5, section 9 |

## 2. Staging or interchange at Scully and Demmler

The brief asks for the options before a choice.

| Option | What it gives | What it costs |
|---|---|---|
| A. Scully and Demmler as **staging** | The offline world for free: arriving custom loads are emptied on terminate, departing empties get generated loads for the island spurs. No STG trains | D749 cannot pass through Demmler mid-turn, so D749 must split in two. Every car on the departure track must leave or the build fails. Generated loads are random, not the STS shipments, and the owner cannot edit them as lines. The interchange swap at South Yard still needs a yard hop |
| B. Scully and Demmler as **interchange**, offline as **staging** | STG trains terminate into staging where loads are emptied and generated | Same departure-must-leave rule on the offline tracks, same random loads, plus two more trains |
| C. Scully and Demmler as **interchange**, offline as a **spur with a schedule** (chosen) | D749 runs as one turn. Offline load and unload are schedule lines the owner edits, one per STS shipment, deterministic and auditable by `ops_why_not`. STG trains swap yard and offline exactly as STS does. Routed cars never scatter | Two virtual trains and two virtual spurs to maintain; four-train routes for IX traffic; the offline spur's length is not physical |

**Decision D5/D6: option C.** Physical fit: the interchange track is the loop half (890 ft); the offline spur is 2000 ft and virtual. Where offline cars physically sit is an open question (Q1).

## 3. Global settings (one plan, first)

| Setting | Value | Why |
|---|---|---|
| `set_control_limits` attribute length | 24 | "Covered Hopper" and the chemical load names exceed JMRI's 12 |
| `buildOptions.aggressive` | true, 2 passes | The island spurs are full between sessions; NVL pulls and spots on the same visit, which normal mode refuses for lack of room. The legacy file had the same |
| `router.carRoutingViaYards` | true | Every D749 ↔ NVL hand-off is a hop through a South Yard yard track |
| `router.carRoutingViaStaging` | false | No staging |
| `router.forwardToYard` | true | Default |
| `buildOptions.allowLocalSpur/Yard/Interchange` | false | No switchers |
| `buildOptions.onTime` | false | On-time order would abort a train built out of order; build order is the automation's job (D21) |
| `settings.trainLength` | 1000 | Default; route stops set their own |
| `settings.lengthUnit`, `scale` | Feet, HO | Track lengths are scale feet: inches × 87.1 ÷ 12, rounded to 5 (D22) |
| Railroad name | `HART Railroad, Pittsburgh & Chartiers Valley Division` | The STS railroad name. Never expand the four letters |
| Active train schedule day | none | D20 |
| Directions | every location, track and stop takes all four | Direction is not used as a filter (D23) |

## 4. Car types, roads and loads

**Car types** (add if the blank file lacks them): `Covered Hopper`, `Coke Hopper`, `Tank`, `Coach`, `Combine`, `Dining`, `Observation`. Already in JMRI's defaults: `Boxcar`, `Hopper`, `Flatcar`, `Coilcar`, `Gondola`, `Reefer`, `Caboose`, `Baggage`, `MOW`. Locomotive type `Diesel`.

**Roads** are registered by `add_car`; nothing to add first.

**Loads** (type: loads; `*` = hazardous):

| Type | Loads |
|---|---|
| Covered Hopper | Pellets, Cement, Carbon, Aggregate, Phosphor Compounds* |
| Hopper | Coal, Aggregate |
| Coke Hopper | Coke |
| Tank | Ethyl Acrylate*, Methyl Methacrylate*, Styrene Monomer*, Caustic Soda*, Hydrochloric Acid*, Phosphoric Acid*, LPG*, Argon*, Industrial Gases* |
| Boxcar | Plastic Resins, Steel, Steel Coils, Machined Parts, Fluorescent Lamps, Fluorescent Tubes |
| Flatcar | Steel, Steel Plate, Railway Springs, Steel Billets, Forgings, Stainless Bar, Stainless Slab |
| Gondola | Steel, Steel Billets, Steel Coils, Aggregate, Scrap Steel |
| Coilcar | Steel Coils, Tin Plate |
| Reefer | Frozen Foods, Packaged Meats |

A plan that adds loads before any track receives them is blocked by `load-no-track` errors; apply it with `accept_new_errors`, which stage 3 clears.

## 5. Locations and tracks

Lengths in scale feet. Measured tracks come from `jmri/layouts/hart/data/block_lengths.csv`; industry spurs are 60 ft per STS spot (D4, estimate until the East End tracks are measured).

| Location | Track | Type | Length | Types | Notes |
|---|---|---|---|---|---|
| West Yard | W-1 | Yard | 760 | all freight, Diesel | 105 in. D749 ties down here |
| West Yard | W-2 | Yard | 675 | all freight, Diesel | 93 in |
| South Yard | S-R | Yard | 1580 | all freight | 218 in, run-through |
| South Yard | S-1 | Yard | 1540 | all freight | 212 in |
| South Yard | S-2 | Yard | 1290 | all freight | 178 in |
| South Yard | S-3 | Yard | 1030 | all freight | 142 in |
| South Yard | S-4 | Yard | 725 | all freight | 100 in |
| South Yard | Scale | Yard | 175 | all freight, MOW | 24 in on the West Lead; `moves` 500 so it is used last (D1); holds the scale test car |
| South Yard | EH-1, EH-2, EH-3 | Yard | 175 each | Diesel only | Engine terminal (D2) |
| Scully Yard | Scully Interchange | Interchange | 890 | all freight, Diesel | Track McKees Rocks loop half, 122.5 in. Set out by and pulled by NVL and STG-SCULLY |
| Demmler Yard | Demmler Interchange | Interchange | 890 | all freight, Diesel | Track McKeesport loop half. Set out by and pulled by D749 and STG-DEMMLER |
| McKees Rocks | POHC Offline | Spur | 2000 | all freight | Virtual. Schedule `POHC Offline`, match mode, hold_custom. Comment: "POHC parties beyond Scully; one line per STS shipment" |
| McKeesport | CSX Offline | Spur | 2000 | all freight | Virtual. Schedule `CSX Offline`, match mode, hold_custom |
| Aristech Plastics | Pellet Unload | Spur | 180 | Covered Hopper | spots 1-3; alternate Off Spot |
| Aristech Plastics | Chemical Unload | Spur | 120 | Tank | spots 4-5; alternate Off Spot |
| Aristech Plastics | Shipping Door | Spur | 60 | Boxcar | spot 6; alternate Off Spot |
| Aristech Plastics | Off Spot | Spur | 60 | Covered Hopper, Tank, Boxcar | spot 7, no schedule |
| Ferrellgas | LPG Unload | Spur | 120 | Tank | spots 1-2; alternate Storage |
| Ferrellgas | Storage | Spur | 60 | Tank | spot 3, no schedule |
| A. Stucki Co. | Crane Track | Spur | 60 | Boxcar, Flatcar, Gondola | spot 1; alternate Off Spot |
| A. Stucki Co. | Team Track | Spur | 60 | Boxcar, Flatcar, Gondola | spot 2; alternate Off Spot |
| A. Stucki Co. | Off Spot | Spur | 60 | Boxcar, Flatcar, Gondola, Coilcar | spot 3, no schedule |
| Kosmos Cement | Cement Unload | Spur | 180 | Covered Hopper | spots 1-3; alternate Off Spot |
| Kosmos Cement | Aggregate Unload | Spur | 60 | Hopper, Gondola, Covered Hopper | spot 4; alternate Off Spot |
| Kosmos Cement | Off Spot | Spur | 60 | Covered Hopper, Hopper, Gondola | spot 5, no schedule |
| Calgon Carbon | Coal Unload | Spur | 120 | Hopper | spots 1-2; alternate Off Spot |
| Calgon Carbon | Carbon Load | Spur | 60 | Covered Hopper | spot 3; alternate Off Spot |
| Calgon Carbon | Chemical Unload | Spur | 60 | Tank | spot 4; alternate Off Spot |
| Calgon Carbon | Off Spot | Spur | 60 | Hopper, Covered Hopper, Tank | spot 5, no schedule |
| Shenango Coke Works | K-1 | Spur | 175 | Coke Hopper | 24 in Princess stub; schedule `Shenango Coke`; pulled by CK1 only; set out by CK1 and NVL |
| Shenango Coke Works | K-2 | Spur | 175 | Coke Hopper | same schedule and lists |

"All freight" means every car type above plus Caboose and MOW; passenger types are left off every track (the passenger cars are not placed, D24). Every industry spur has `hold_custom` on so a car whose spur is full waits in the yard instead of scattering (D25). Island spurs get the Off Spot alternate; the alternate has no schedule and excludes the default loads E and L, because JMRI sets default-load cars out directly on an alternate (seen in the ordered test). The two offline spurs carry move count 1000 so that a loaded car with no final destination prefers an island spur in the custom-load search.

Island order along the East End ladder (station map): Aristech Plastics, Ferrellgas with A. Stucki Co. on the same physical track, Kosmos Cement, Calgon Carbon, then Shenango at Princess.

## 6. Industries and schedules

`add_industry` makes the spur and its schedule in one step; K-2 and the Off Spot tracks are `add_track` (K-2 naming the `Shenango Coke` schedule). The lines are in [`opspro-build/island_schedule_lines.csv`](opspro-build/island_schedule_lines.csv) (28 lines over 11 spurs) and [`opspro-build/offline_schedule_lines.csv`](opspro-build/offline_schedule_lines.csv) (84 lines over the two offline spurs). A blank `ship` means the car leaves empty; the line's destination sends it back to the offline side STS used for that industry's empties. Every receive load is explicit, never blank, so a car's load alone decides which spur and which side takes it (D26). All schedules are match mode.

How a shipment flows, for a cement car: CSX Offline line `E → Cement, Kosmos Cement / Cement Unload` loads it and sets the final destination; STG-DEMMLER sets it out on Demmler Interchange; D749 takes it to a South Yard yard track (router, via yards); NVL spots it at Cement Unload, where the line `Cement → (empty), McKeesport / CSX Offline` sends it back; NVL leaves it at South Yard; D749 takes it to Demmler; STG-DEMMLER delivers it to CSX Offline, where the next line loads it again.

## 7. Routes, trains and the session

| Train | Departs | Route (stop: moves) | Engines | Notes |
|---|---|---|---|---|
| D749 | 07:00 | Demmler Yard (pick up only: 20) → West Yard (no pick ups or set outs: 1) → South Yard (20) → Demmler Yard (set out only: 20) | 1, road CR, model B23-7 | Description "CSX Neville Island Switcher". The Demmler pick-ups are the block already on the train from the night before; the West Yard stop is the tie-down point and raises the intended `route-stop-dead` warning |
| NVL | 08:00 | Scully Yard (20) → South Yard (20) → Aristech Plastics (8) → Ferrellgas (3) → A. Stucki Co. (4) → Kosmos Cement (5) → Calgon Carbon (5) → Shenango Coke Works (3) → South Yard (20) → Scully Yard (20) | 1, road POHC, model GP20 | "Neville Island Turn" |
| CK1 | 09:00 | South Yard (pick up only: 8) → Shenango Coke Works (8) → South Yard (set out only: 8) | 0 | "Coke Transfer. Power assigned by the Yardmaster" |
| STG-DEMMLER | 16:00 | Demmler Yard (pick up only: 30) → McKeesport (30) → Demmler Yard (set out only: 30) | 0 | Virtual: CSX offline swap, run by the automation |
| STG-SCULLY | 17:00 | Scully Yard (pick up only: 30) → McKees Rocks (30) → Scully Yard (set out only: 30) | 0 | Virtual: POHC offline swap |

Max train length 1000 ft at every stop. Trains take every car type and road (`add_train` default); the track type lists do the fencing. Interchange lists are set with `setup_interchange` after the trains exist. Cabooses are not required (D27).

**Session order** (the brief's four questions):

1. Build order: D749, then NVL once D749 has reached South Yard, then CK1. The STG trains build at session end. On-time mode is off; the automation fixes the order (D21).
2. Terminate order: NVL and CK1 terminate before D749, which ties down last at West Yard. Stage 4 confirms in a dry run that this leaves D749's cars intact and that cars freed by NVL and CK1 are seen only by trains built afterwards (the STG trains).
3. Groups: {D749} → {NVL, CK1} → {STG-DEMMLER, STG-SCULLY}. Wait-for-terminate steps separate the groups.
4. Days: one pattern, no day activation (D20).

**Automation `Session`** (the live one; no step opens a window):

1. build_train D749
2. wait_for_train D749 at South Yard (the dispatcher moves D749 when the crew arrives)
3. build_train NVL
4. build_train CK1
5. wait_for_train_to_terminate NVL
6. wait_for_train_to_terminate CK1
7. wait_for_train_to_terminate D749
8. build_train STG-DEMMLER, terminate_train STG-DEMMLER
9. build_train STG-SCULLY, terminate_train STG-SCULLY

**Automation `Session Replay`** (for tests and dry runs, needs no one at the layout): build D749; move D749 to South Yard; build NVL; build CK1; terminate NVL; terminate CK1; terminate D749; build and terminate STG-DEMMLER; build and terminate STG-SCULLY. No startup automation (D28).

## 8. Cars and locomotives

[`opspro-build/car_start_positions.csv`](opspro-build/car_start_positions.csv): 99 cars from the repository, with type, length, weight, built date, colour, out-of-service flag, STS status and location, the Operations Pro start track, the method and the load.

- `place`: `add_car` on the track, then `update_car` with the load when it is not E.
- `deliver`: `add_car` on the interchange of that side (Scully Interchange for McKees Rocks and the island, Demmler Interchange for McKeesport), set the load, then `ops_deliver_car` to the start track so the schedule runs and the car gets its next load and final destination, as Set Car would. The STS load is kept where a receive line exists for it; otherwise the car is delivered empty (D29).
- `none`: `add_car` with no location. These are the 28 cars STS does not hold (passenger cars, cabooses, no-photo freight cars) and HART 1776 (D24).

Cars STS had on D749 at session end sit on Demmler Interchange with CR 1993: on paper D749 departs Demmler with them, physically the train is tied down in West Yard. Ten cars are out of service (repository flag, STS Unavailable).

Locomotives (road, number, model, type Diesel, length, hp, start track):

| Engine | Model | Length | HP | Start |
|---|---|---|---|---|
| CR 1993 | B23-7 | 62 | 2250 | Demmler Interchange (D749's power; on paper the train departs Demmler, physically it sleeps in West Yard) |
| POHC 2091 | GP20 | 56 | 2000 | Scully Interchange (NVL's power) |
| BO 9602 | SW1200 | 45 | 1200 | South Yard EH-1 |
| BO 572 | NW2 | 45 | 1000 | South Yard EH-1 |
| BO 3840 | GP38 | 59 | 2000 | South Yard EH-2 |
| BO 3545 | GP35 | 56 | 2500 | South Yard EH-2 |
| BO 6944 | GP30 | 56 | 2250 | South Yard EH-3 |
| BO 2235 | AS-16 | 56 | 1600 | South Yard EH-3 |
| CO 8216 | U30B | 60 | 3000 | South Yard EH-3 |
| CSX 1827 | ES44AH | 74 | 4400 | no location (display unit) |

The crew card gives NVL's engine as POHC 2091 and the repository as CWRY 2091; the crew card wins (D30). Streetcar 4678 (Route 23) is not Operations data and is left out.

## 9. What Operations Pro cannot reproduce (deliverable 5)

| STS behaviour | Nearest substitute |
|---|---|
| Per-step destination pick-up criteria | Router plus interchange train lists (D11). A car's train is chosen by its final destination, not by a step list |
| Track scale: weigh, pass or reject, reload order | CK1 sets coke out at South Yard; the scale is a yard track used last. A rejected car is sent back with `ops_deliver_car` or Set Car to K-1. Route comment on CK1's South Yard stop says to weigh on the West Lead scale |
| Order generation with intervals and amounts | Schedule lines with `random`; the mirror spur reloads every car that arrives, so supply equals the fleet |
| 46 named offline parties | One spur per side; the party is the line's `sts_shipment` comment and the load name |
| Colour-coded destination blocks on paperwork | Manifest colours are per line kind, not per destination. Location comments carry the colour word (BLUE, YELLOW, ...) and print on manifests |
| D749's engine hostled to the engine terminal mid-session | Not modelled; the engine stays with the train |
| D749 Return as a separate lineup entry | The last leg of D749's route |
| Session number in headers | The JMRI date on the manifest |
| Warm start simulation | Dry runs on a copy |
| Car cards and waybills (hart-ops) | Manifests and switch lists; the card pipeline is separate |

## 10. Keeping the cars and the Operations folder in step (deliverable 6)

ADR-013 makes `external/hart-ops/data/image_metadata.csv` the one car repository and ADR-015 makes `jmri/layouts/hart/operations/` the master of the six files. Proposal:

1. `bin/cars publish` keeps adding cars to `OperationsCarRoster.xml` and never replaces it, as today. It should derive the Operations type the way `car_start_positions.csv` does: the STS car code first (HC/HP → Covered Hopper, HM/HT/HK → Hopper, the coke-fleet list → Coke Hopper, TA → Tank, FC → Coilcar), then the repository's `car_type` and `car_class` (LO → Covered Hopper). Record the coke fleet in the repository (a `pool` column) rather than in the seed config, so both tools read it.
2. A new car gets no location; the owner places it in JMRI or with `place_car`. Publishing never moves a car.
3. `out_of_service` keeps flowing from the repository to both tools (ADR-015 item 5).
4. `bin/cars compare` should add a check that every car in the roster is in the repository and that type, length and weight agree, with the type mapping above. Differences stay reported, not fixed, as ADR-013 says.
5. Session state (locations, loads, final destinations) belongs to JMRI on the Pi: `make ops-pull` before a deploy, as ADR-015 says. The build in this branch replaces the legacy folder once, and after that only `ops-pull` and `publish` write to it.
