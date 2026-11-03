# HART Operations Pro: dry-run report

Deliverable 4 of [`OPSPRO_BUILD_PROMPT.md`](OPSPRO_BUILD_PROMPT.md), written 2026-11-02 against the folder as shipped on branch `agent/claude/opspro-build` after the owner's review. Two kinds of test were run on copies; the shipped files were not built in.

- **`ops_dry_run`**: the plugin's one-pass test. Every train is built from the same start state and then terminated. It shows gates and routing, not hand-offs, and it cannot build D749 Return (its engine is still on D749 at West Yard in that state).
- **Ordered session**: nine chained jobs through the plugin's JMRI worker (a script since replaced by `ops_dry_run` with `order`; see [`OPSPRO_FOLLOWUP.md`](OPSPRO_FOLLOWUP.md)), each building and terminating its trains and saving for the next, in the order of the `Session` automation's groups, without its overlap (see [`OPSPRO_FOLLOWUP.md`](OPSPRO_FOLLOWUP.md)): D749; NVL and CK1; STG-DEMMLER; D749 Return; STG-SCULLY; then session 2 the same way up to D749 Return. This is the test that counts. Per-train rows: [`opspro-build/ordered_session.csv`](opspro-build/ordered_session.csv).

## Each train

"Partial" is JMRI's word for a build that used fewer moves than the route offered; in the ordered session every train builds and none fails.

| Train | Ordered session 1 | Ordered session 2 | Engine |
|---|---|---|---|
| D749 | 13 cars: the overnight block (2 Steel Plate) set out at South Yard; 11 cars (Tin Plate and empties) to Demmler | 21 cars: Coal and 2 Steel Coils from West Yard to South Yard; Coke, Carbon, Lamps, Tubes, Plastic Resins, Tin Plate and empties to Demmler | CR 1993 |
| NVL | 22 cars: 9 from Scully (Lamps, Tubes to South Yard; an empty to K-1); pulls at Aristech, Calgon, Kosmos, A. Stucki; **the 2 Steel Plate cars D749 set out picked up at South Yard**; outbound block to Scully | 18 cars: Coal to Calgon (2), MMA to Aristech Chemical Unload (2, a third to its Off Spot), Pellets to Pellet Unload (2), Steel to Crane Track and Off Spot, Steel Coils to Team Track, an empty to Shipping Door, 3 empties to K-1; 2 Coke to Scully | POHC 2091 |
| CK1 | 3 coke loads from K-1 and K-2 over the scale to South Yard | 1 coke load out, 3 empties to K-2 | BO 3545, then BO 6944, from the EH tracks |
| STG-DEMMLER | 18 cars: 12 off to CSX Offline, Coal, 2 Steel Coils and 3 empties back | 25 cars: 13 off (Carbon, Coke, Lamps, Tubes, Resins, Tin Plate, empties), 12 back loaded (Coal, Aggregate, Pellets, Steel Plate, Steel, Steel Coils, Packaged Meats) | none |
| D749 Return | 8 cars: Coal, 2 Steel Coils and 5 empties from Demmler, tied down in West Yard | 13 cars: Coal, Aggregate, Pellets, Steel Plate, Steel, Steel Coils, Packaged Meats to West Yard | CR 1993 |
| STG-SCULLY | 23 cars: 9 off to POHC Offline, 14 back (Coal, 3 MMA, 2 Pellets, Steel Coils, 2 Steel, 5 empties) | not run | none |

One-pass dry run on the same files: D749 13 cars, NVL 20, CK1 3 (engine BO 3545), STG-DEMMLER 6, STG-SCULLY 8; D749 Return fails A9 because CR 1993 is at West Yard until D749 terminates, which is the ordered case. Cars refused in the one-pass run: out-of-service cars (B3) everywhere; the three coke cars on NVL (B7, pulled by CK1 only); cars on the offline spurs held for room on an interchange nobody had pulled yet (E9); CO 306607 and EL 66410 held for a scheduled spur. In the ordered session those holds disappear.

## What the ordered session proves

1. **The hand-off works.** NVL picked up at South Yard the cars D749 set out there; D749 took away what NVL and CK1 left.
2. **The return carries the fresh block.** D749 Return built after the Demmler swap and took the loads STG-DEMMLER had just brought in (Coal, Steel Coils; then Aggregate, Pellets, Steel Plate, Steel, Packaged Meats) to West Yard, and the next morning's D749 delivered them to South Yard for NVL.
3. **Coke flows both ways.** CK1 brings coke over the scale to South Yard; D749 takes it to Demmler and NVL to Scully; the offline lines send the hoppers back empty to K-1 and K-2.
4. **Empties reposition.** Default empties at South Yard ride D749 to Demmler and NVL to Scully, go offline, and come back loaded, as STS's reposition step does.
5. **Terminate order.** D749 terminated at Demmler before the swap; NVL, CK1 and D749 Return terminated before STG-SCULLY; nothing was lost.
6. **Capacity.** With the South Yard tracks halved (790 to 365 ft) nothing ran out of room; Scully Interchange (890 ft) took every car once NVL had pulled it.

Found and fixed by the earlier ordered runs (D8, D34, D35 in [`OPSPRO_OPEN_QUESTIONS.md`](OPSPRO_OPEN_QUESTIONS.md)): a one-train D749 ending at West Yard delayed Demmler inbounds and parked empties; default empties landed on the Off Spot alternates; loaded flatcars with no final destination went offline.

## Audit findings that remain

| Rule | Severity | Count | Why it stays |
|---|---|---|---|
| type-no-track | error | 5 | Baggage, Coach, Combine, Dining, Observation: types for the unplaced passenger cars (D24, confirmed by the owner) |
| car-unplaced | warning | 29 | Cars STS does not position (D24) |
| route-stop-dead | warning | 1 | CK1's Scale stop weighs and does no work (D1) |
| train-not-on-list | info | 4 | D749 sets out only and D749 Return pulls only at Demmler; K-1 and K-2 are pulled by CK1 only |

## Known limits of the test

- The ordered session chains the plugin's JMRI worker from a script; `ops_dry_run` cannot order trains or terminate between builds (fault F22), and its startup-automation run leaves no trace (F24). The live test of the `Session` automation on the Pi is still owed.
- JMRI logs "Schedule missing for car ... to spur (Off Spot)" as an error when a car overflows to an alternate; the move is correct (F25).
- Two Steel Plate flatcars placed loaded without a final destination went to Scully and offline in session 1 and were reloaded as Steel for A. Stucki; cars delivered through a schedule do not do this.
