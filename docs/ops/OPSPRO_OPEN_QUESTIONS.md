# HART Operations Pro: decisions to review and open questions

Written 2026-11-02 during the unattended build ([`OPSPRO_BUILD_PROMPT.md`](OPSPRO_BUILD_PROMPT.md)). The owner asked for no approval stops, so every missing fact got the most defensible default. Each decision below says what was chosen and why, so it can be reversed. D numbers match [`OPSPRO_MAPPING.md`](OPSPRO_MAPPING.md).

## Decisions made without asking

| # | Decision | Reason | To reverse |
|---|---|---|---|
| D1 | The track scale is a yard track `Scale` at South Yard with move count 500 | Operations Pro has no scale; a yard track used last keeps it on the switch list without attracting set outs | Delete the track; move the scale test car |
| D2 | The engine terminal is three Diesel-only yard tracks EH-1..3 inside South Yard, not a separate location | CK1 and the yardmaster are at South Yard; a separate location would need a route stop | `delete_track` and `add_location Engine House` |
| D3 | One Operations location per island industry, not one "Neville Island" location | The crew documents and Route 23 timetable treat them as stations; colour blocks are per industry | Merge later; the schedule lines move with the tracks |
| D4 | Industry spur length is 60 ft per STS spot; Off Spot and Storage are alternates of 60 ft | The East End tracks have no measured length in `block_lengths.csv`; 60 ft fits one 50 ft car with couplers | `update_track length` once measured |
| D5 | Scully and Demmler are interchange tracks, not staging | D749 passes through Demmler mid-turn; staging cannot be a middle stop | Rebuild with staging and split D749 |
| D6 | The offline world is one spur per side (POHC Offline, CSX Offline) with a match-mode schedule, 2000 ft, virtual | Deterministic, editable one line per STS shipment, no departure-must-leave rule | Convert to staging with `setup_custom_staging` |
| D7 | North Yard and East Yard are not built | No cars, no measured tracks, STS calls East Yard reserved; CK1's crew card starts at South Yard | `add_location` and a CK1 stop |
| D8 | D749 is one train, West Yard → South Yard → Demmler Yard → West Yard | The crew card describes one turn; the inbound block picked up at Demmler ties down at West Yard | Fallback if the three-train route fails in stage 4: D749 built at session end from Demmler, tying down at West Yard, with the block set out at South Yard next session |
| D9 | K-1 and K-2 are pulled by CK1 only; NVL may set out there | STS gives coke pulls to CK1 and lets NVL deliver | `update_track pickup` |
| D10 | STG-SCULLY and STG-DEMMLER stay as trains with no engine, built and terminated by the automation at session end | They are the offline swap STS runs between sessions | Delete them and use staging (D5) |
| D11 | Per-step pick-up criteria are replaced by the router with car routing via yards on, and interchange train lists | No per-stop destination filter exists | Nothing to reverse; it is the program |
| D12 | STS shipments became schedule lines; 84 offline and 28 island lines | One line per shipment keeps the owner's editing surface | Edit the lines |
| D13 | Chemicals keep their real names as loads and are flagged hazardous; the general "Process Chemicals" code is not a load | The waybills name them and the seed config carries placards | `rename_load` or merge |
| D14 | Two open hopper types: `Hopper` (coal, aggregate) and `Coke Hopper` (the 16 coke-fleet cars from the seed config) | Keeps coal cars off the coke ovens and coke cars off the coal unload | `rename_car_type` to merge |
| D15 | Rare IX lines carry `random` 50; island lines none; STS intervals not copied | Balance is tuned by dry runs | Edit `random` |
| D16 | Empties return to the side STS names: Aristech and Calgon to McKees Rocks, A. Stucki, Ferrellgas and Kosmos to McKeesport | `outbound_empty_return` in the seed config | Edit the line destinations |
| D17 | No divisions | The line destinations already say where empties go | `add_division` later |
| D18 | No warm start; the start state is the STS session 3 end | The brief names that dump as the source | Replay sessions and `ops_restore` |
| D19 | Two automations: `Session` with wait steps for the live day, `Session Replay` that moves and terminates for tests | A wait needs someone at the layout; a dry run needs no one | Delete one |
| D20 | No train schedule day is active | One session pattern | `add_day`, `set_active_day` |
| D21 | On-time build mode off | A train built out of order would abort | `set_option` |
| D22 | Track length is scale feet: inches × 87.1 ÷ 12, rounded to 5 | JMRI's length unit is feet and cars are entered in scale feet | Re-enter lengths |
| D23 | Every location, track and stop takes all four directions | Direction is not needed as a filter on a loop with turns | Set directions per track |
| D24 | The 28 cars STS does not position (passenger cars, cabooses, no-photo freight cars) and HART 1776 are in the roster with no location | No evidence where they stand; the legacy roster left them unplaced too | `place_car` |
| D25 | `hold_custom` on every industry spur and both offline spurs | Without staging, a full spur would scatter cars onto yards | `update_track hold_custom false` |
| D26 | Offline lines use explicit receive loads, never blank | A car's load alone then decides its side and spur | Add blank-receive lines |
| D27 | No caboose or FRED requirement on any train | The crew cards show none | `update_train requires` |
| D28 | No startup automation | A startup automation runs on every computer that opens the folder | `set_startup_automation` |
| D29 | Cars at offline spurs and island spurs are delivered through the schedule, so their load is whatever the next line gives, not the exact STS order | The schedule is the only way to give a car a final destination | `update_car load` |
| D30 | NVL's engine is POHC 2091 (crew card), not CWRY 2091 (repository); the ten locomotives get models with lengths and horsepower from public data | The crew card is the owner's latest word | `update_engine` |

## Open questions for the owner

| # | Question | Default taken |
|---|---|---|
| Q1 | Where do offline cars physically sit: on the loop with the interchange block, or lifted off the layout? If on the loop, the 890 ft loop is shared and the 2000 ft offline spur overstates capacity | Virtual 2000 ft |
| Q2 | Real lengths of the East End industry tracks (station map S-2 to S-5) and whether each STS spot is a separate physical spot | 60 ft per spot |
| Q3 | Should the no-photo freight cars (BO 1604, BO 9151, BO 9300, CO 18729, GN 68560, MILW 61032, PRR 153958, PRR 727454, UTLX 35294, WP 56057) and HART 1776 enter service, and where | Unplaced |
| Q4 | Should CK1 require an engine (which road) rather than "Yardmaster assigns" | 0 engines |
| Q5 | Is the coke fleet list in the seed config still right (16 cars)? BO 11027 and BO 11137 were sitting empty at Aristech Chemical Unload in STS, which looks like a data slip; they start at K-2 | Seed config list |
| Q6 | Should D749's engine change at the engine terminal be shown (a second leg with a locomotive change at South Yard) | Not modelled |
| Q7 | Manifest wording: does the owner want the colour word (BLUE, YELLOW...) in location comments printed on manifests, or a separate yardmaster switch list only | Both: comments on, switch lists on for South Yard |
| Q8 | Which day name should the session carry, if any, for the manifest header | None |
| Q9 | Is "A. Stucki Co." or "A Stucki Co" the name to print (crew card vs STS) | Crew card: "A. Stucki Co." |
| Q10 | Should Route 23 (streetcar 4678) and the passenger OCS-1 train be in Operations at all | Left out |
