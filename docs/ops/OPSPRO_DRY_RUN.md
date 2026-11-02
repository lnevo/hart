# HART Operations Pro: dry-run report

Deliverable 4 of [`OPSPRO_BUILD_PROMPT.md`](OPSPRO_BUILD_PROMPT.md), written 2026-11-02 against the folder as shipped on branch `agent/claude/opspro-build`. Two kinds of test were run on copies; the shipped files were not built in.

- **`ops_dry_run`**: the plugin's one-pass test. Every train is built from the same start state and then terminated. It shows gates and routing, not hand-offs.
- **Ordered session**: five chained jobs through the plugin's JMRI worker ([`opspro-build/ordered_session.py`](opspro-build/ordered_session.py)), each building and terminating its trains and saving for the next: D749; NVL and CK1; STG-DEMMLER and STG-SCULLY; then D749 and NVL and CK1 again as session 2. This is the session order the automations use, and it is the test that counts. Per-train rows: [`opspro-build/ordered_session.csv`](opspro-build/ordered_session.csv).

## Each train

"Partial" is JMRI's word for a build that used fewer moves than the route offered; here every train builds and none fails.

| Train | One-pass dry run | Ordered session 1 | Ordered session 2 | Engine |
|---|---|---|---|---|
| D749 | Built, 20 cars: 7 Demmler pick-ups set out at South Yard, 13 South Yard cars to Demmler | 20 cars: the overnight block (2 Steel Plate, 5 empties) to South Yard; 13 cars (2 Tin Plate, 11 empties) to Demmler | 18 cars: Coal and 2 Steel Coils from Demmler to South Yard; Coke, Carbon, Lamps, Tubes, Plastic Resins and empties to Demmler | CR 1993 |
| NVL | Built, 17 cars | 24 cars: 9 from Scully (Lamps, Tubes to South Yard; an empty to K-1); pulls at Aristech, Calgon, Kosmos, A. Stucki; **2 Steel Plate set out by D749 picked up at South Yard**; 2 empties to the coke tracks; outbound block to Scully | 17 cars: Coal to Calgon Coal Unload, 2 MMA to Aristech Chemical Unload (a third to its Off Spot), 2 Pellets to Pellet Unload, Steel to Crane Track and Off Spot, Steel Coils to Team Track, 2 empties to K-1; 2 Coke and empties to Scully | POHC 2091 |
| CK1 | Built, 3 coke loads to South Yard | 3 coke loads from K-1 and K-2 to South Yard | 3 coke loads to South Yard, 2 empties to K-2 | none, by design |
| STG-DEMMLER | Built, 0 cars (Demmler Interchange full in one pass: 6 held for room, E9) | 19 cars: 13 off to CSX Offline, Coal, 2 Steel Coils and 3 empties back | not run | none |
| STG-SCULLY | Built, 11 cars; 3 held for room (E9) | 23 cars: 9 off to POHC Offline, Coal, 3 MMA, 2 Pellets, Steel Coils, 2 Steel, 5 empties back | not run | none |

Cars refused and why, one-pass run: the out-of-service cars (B3) on every train; the three coke cars on NVL (B7, pulled by CK1 only); six cars on CSX Offline and three on POHC Offline for room on the interchange (E9), because the one-pass test builds the STG trains before D749 or NVL has pulled the interchange. In the ordered session the interchanges empty first and those holds disappear. NYC 47516 (an empty at South Yard) was left for room at Demmler in the one-pass run; EL 66410 (Plastic Resins) was held for a scheduled spur, correctly.

## What the ordered session proves

1. **The hand-off works.** NVL picked up at South Yard the two cars D749 had set out there, and D749 took away what NVL and CK1 left.
2. **Coke flows both ways.** CK1 brings coke to South Yard; D749 takes it to Demmler and NVL to Scully; the STG trains deliver it offline, where the mirror lines send the hoppers back empty to K-1 and K-2.
3. **Offline loads reach the island next session.** Coal, Pellets, Methyl Methacrylate, Steel and Steel Coils loaded at the offline spurs in session 1 were spotted at Calgon, Aristech and A. Stucki in session 2.
4. **Empties reposition.** Default empties at South Yard ride to the interchanges, go offline, and come back loaded, as STS's reposition step does.
5. **Terminate order.** NVL and CK1 terminated before D749 in every job, D749's cars were intact, and the STG trains saw only cars the crewed trains had freed.
6. **Capacity.** Scully Interchange (890 ft) took every car once NVL had pulled it; the one-pass holds were an artefact of that test.

Found and fixed by the first two ordered runs (decisions D8 revised, D34, D35 in [`OPSPRO_OPEN_QUESTIONS.md`](OPSPRO_OPEN_QUESTIONS.md)): a West Yard terminal for D749 delayed every Demmler inbound by two sessions and parked thirteen empties; default empties were set out on the Off Spot alternates; two loaded flatcars with no final destination went offline instead of to A. Stucki.

## Audit findings that remain

| Rule | Severity | Count | Why it stays |
|---|---|---|---|
| type-no-track | error | 5 | Baggage, Coach, Combine, Dining, Observation: types for the unplaced passenger cars (D24) |
| car-unplaced | warning | 29 | Cars STS does not position (D24, Q3) |
| engine-no-train | warning | 8 | Spare and display locomotives at the engine house |
| route-stop-dead | warning | 1 | D749's West Yard tie-down stop does no work on purpose |
| train-not-on-list | info | 2 | K-1 and K-2 are pulled by CK1 only (D9) |

## Known limits of the test

- The ordered session chains the plugin's JMRI worker from a script; `ops_dry_run` cannot order trains or terminate between builds (fault F22), and its startup-automation run leaves no trace (F24). The live test of the `Session` automation on the Pi is still owed.
- JMRI logs "Schedule missing for car ... to spur (Off Spot)" as an error when a car overflows to an alternate; the move is correct (F25).
- Two Steel Plate flatcars placed loaded without a final destination went offline in session 1 and were reloaded as Steel for A. Stucki; cars delivered through a schedule do not do this.
