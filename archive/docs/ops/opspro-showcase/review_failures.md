# Guide review: failures and open points

Scope: every behavioural claim in `GUIDE.md` (201 after splitting compound sentences; see `claims.csv`). Evidence folders are under `runs/`: `base` is the untouched shipped data, `chain3` is three consecutive real JMRI sessions on it (`tools/run_sessions.py`), `e_*` are the Try-this copies, `e_*_run` their sessions. Source line numbers refer to JMRI v5.16 under `java/src/jmri/jmrit/operations/`.

Totals: 181 PASS, 17 FAIL, 3 UNVERIFIED (C165 counted as FAIL with C109).

## FAIL

### C006 (How to use it): "Every object a case uses has its code in its comment ... schedules"
- What is true: cars, locations, routes, trains and automations all carry a code. Ten schedules do not: ids 1 and 32 to 40 (Linden Steel, Linden Pier, Linden Glazier, Linden Pipe Yard, Linden Westside, Carrow Salt Works, Carrow Glass Works, Sawyer Pasta Plant, Brae Depot, Dunmere Depot) have `comment=""` although U04, U06, U22, R03, R05, R14 and R15 use them.
- Evidence: `OperationsLocationRoster.xml` schedule elements (dump in `notes/locations.txt` lines 424-504).
- Fix: add the codes to those ten schedule comments, or reword to "cars, locations, trains, routes and automations; most schedules".

### C008 / C201 (How to use it, Known limits): default-E boxcars "are drawn to the Fiddle yard and Dunmere Yard"
- What is true over three sessions (`runs/chain3/state_s2.txt`, `state_s3.txt`): Fiddle takes JFN 1001, 5101, 6401 and 6402 by session 3. Dunmere Yard takes no JFN boxcar at all. Carrow Box Factory (road JFN, receives E) takes JFN 301, 611 and 612 in session 2 and 3; Carrow Glass Works takes JFN 201, 302, 613; Carrow Salt Works takes JFN 102, 901, 902. The guide names Salt Works and Glass Works but not Box Factory.
- Rewording: "After session 1 some cars shuttle on: default-E JFN boxcars of the Brae and Dunmere cases are drawn to the Fiddle yard, Carrow Box Factory and Carrow Glass Works, and empty JFN covered hoppers to Carrow Salt Works." Drop "Dunmere Yard" in both places.

### C012 / C197 (Intended audit findings, Known limits): why the three `single-destination-schedule` warnings are false positives
- Guide: each destination spur has a road list (JFN or OAKX) and the audit samples the first car of the type in the file.
- What is true: Grain Elevator (12s3), the destination of Grain Co Loads, has no road list (`OperationsLocationRoster.xml` track 12s3). The audit's own message reads "Every line sends cars to Dunmere, and no chain of trains takes Parts there" / "...to Northwood, and no chain of trains takes Wheat there" (`ops_audit` on `runs/base`), which is a routing reason, not a road one. The sampling mechanism could not be checked without the plugin source. The deliveries themselves do happen (C013).
- Rewording: "False positives of the audit: it finds no train chain for Parts, Tools or Wheat to the destination, yet the build delivers every one of these cars (U08 and R10 below)." Drop the road-list and first-car explanation unless someone confirms it from the audit code, and drop the matching Known-limits bullet.

### C032 (U03): "`ops_why_not` WNDR 1 to Brae Lumber fails D7 first, then E2, E3, E4, E10 and F2"
- True only with `LOCAL-B` named. With no train named (as the guide reads) the tool picks CUSTOM and reports first_failure D1; LOCAL-B appears in `other_trains` with "D7: Brae: type Coal". The E gates are as stated.
- Rewording: "`ops_why_not` WNDR 1 to Brae Lumber with `LOCAL-B` named fails D7 first ...".

### C047 (U06 Try this): remove both depot schedules
- Guide: `ops_plan` reports `generator-no-target` (info); the car is sent toward East Swap.
- What is true (`runs/e_u06`, `runs/e_u06_run/s1`): the plan reports only two `schedule-unused` infos, no `generator-no-target`. The dry run does not fail, the report has "Could not find a route to a spur that needs a custom load for car (JFN 601)" (line 491) and "Try to send car (JFN 601) to staging, found 10 tracks" (line 492), and the car leaves with Machinery and final destination East Staging, East Mixed (not East Swap).
- Rewording: "remove both depot schedules. `ops_plan` reports only `schedule-unused` (info) twice. The dry run does not fail: West Custom also generates for any staging track, so the car is given a load and sent toward East Mixed (the build report lines ...)."

### C056 (U08): "`ops_why_not` JFN 801 to Fiddle South: F5 not_checked 'line 8c1 random 25%'"
- The tool says "line 9c1 random 25%" (`runs/base`). 8c1 is Fiddle North's line and has no random.
- Fix: 8c1 -> 9c1.

### C064 (U10): "F4 ('line 12c1 receives Crates, car has E')"
- The tool says "line 13c1 receives Crates, car has E"; 12c1 is Grain Receiving. Gates E10, F4 and D16 are right.
- Fix: 12c1 -> 13c1.

### C073 (U12): "the loco change takes two of Brae's three moves"
- What is true: the shipped MODE report line 247 reads "Route location (Brae) id 5r2 requests 2 moves, 2/3 moves are available" after the build, and cars see "0/3 moves used" then "1/3 moves used" at Brae (lines 177-241). The engine change consumed no moves: `trains/trainbuilder/TrainBuilderEngines.java:876-900` `addEngineToTrain` never touches route-location moves. One car went to Brae because the builder alternated the others to East Mode, not because moves ran out.
- Fix: drop the parenthesis, or "(one of Brae's three moves is used; the builder sends the rest on to staging)".

### C089 (U14 Try this): "F1 'line 1c1 set out day Tuesday, active Saturday'"
- The tool says "line 15c1 ..." (`runs/e_u14`). Everything else in the sentence holds, including "Applied Saturday: 6 trains to build, 12 not" and the six-train build.
- Fix: 1c1 -> 15c1.

### C109 / C165 (U19, R10): "`ops_list` tracks shows the pool fields"
- `ops_list tracks` on `runs/base` shows `"pool": "Hollis Pool"` (and "Ferris Pool") but no minimum or maximum length field.
- Rewording: "`ops_list` tracks shows the pool name; the minimum and maximum lengths are in `OperationsLocationRoster.xml` (`minLength`, `maxLength`)."

### C136 (R02 Try this): "In a build the car is sent to Hop instead of waiting"
- `runs/e_r02` dry run: JFN 5201 is on no train; EAST FREIGHT's report says "JFN 5201 no destination: decided by G12". The plan block, the warning and the G12 text are as stated.
- Rewording: "In a build the car stays at Carrow Packing with no destination."

### C147 (R05 Try this): "the real build leaves the car at Carrow Salt Works"
- `runs/e_r05` dry run: EAST FREIGHT leaves it, but `LOCAL-B` (09:00, before EAST FREIGHT) carries JFN 5501 to Dunmere Yard, which takes JFN covered hoppers. The router and G12 parts are as stated.
- Rewording: "EAST FREIGHT no longer takes the car; in a full session `LOCAL-B` carries it to Dunmere Yard instead."

### C154 (R07 Try this): "the session 2 build carries nothing"
- `runs/e_r07` (session 1 state, pick ups Any): NORTH JOB builds "Partial 11/35 cars" (the R02, R06, R08, R10 and U21 cars) and lists "Excluded before the search: B6 XFRX 1". B6 fails as stated; source `TrainBuilderBase.java:1526-1533`.
- Rewording: "and the session 2 build leaves XFRX 1 behind."

### C168 (R11): "`ops_why_not` KESX 1 to Kessock Class 1: D19 pass"
- On the shipped state the car is at Carrow, so the tool reports first_failure B0 "car at Carrow; not on this route" and D19 not_checked. D19 passes on the session 1 state (`runs/chain3/s1`), as R07 says for its own check.
- Rewording: "`ops_why_not` KESX 1 to Kessock Class 1 on the session 1 state: D19 pass."

## UNVERIFIED

### C018 (Intended audit findings): "Naming the allowed trains instead raised 202 such infos"
- A historical figure; reproducing it means rewriting every track list. Not checked. Keep or drop as the author likes; it is not load-bearing.

### C114 / C115 (U20 Try this): the A2 message and the departure-at-11 fix
- The JMRI half is supported by source: `trains/Train.java:3191-3196` returns with `CODE_ERROR` before `reset()` and the build (so no report), and `trains/TrainManager.java:1114-1118` logs one error line when build messages are off. The `ops_why_not` A2 text needs a state with LOCAL-H built and LOCAL-B not; none of the allowed tools builds one train and saves (the session runner builds all in time order, and with on-time on all 18 still build, `runs/e_u20`). On a state with nothing built A2 passes with "no train with a departure time is built".
- Suggest: keep, but say the A2 text is from a hand-built state, or drop the quoted minute numbers.

## Things in the database the guide should mention

1. No railroad name is set in `Operations.xml` (no `railroad` element). Every manifest except LOCAL-B therefore starts "My JMRI Railroad", the JMRI web-server default (`setup/Setup.java:661-666`). U17's "FIDDLE JOB prints the railroad's own name" is literally true but a reader expects a name they can find in the data.
2. Carrow Box Factory (JFN boxcars, receives E, ships Boxes to Routed Siding) is the main sink for default-E JFN boxcars from session 2 on (see C008). It belongs in the "Interactions kept on purpose" bullet.
3. Ten schedules carry no case code (C006).
4. `ops_why_not` A8 gap: with Brae Engine Track at ignore_used_percent 0 the MODE build fails A8 ("Could not find a departure staging track at West Staging that meets the train requirements"), yet `ops_why_not` MODX 1 on the same copy says A8 pass "can depart from West Mode" (`runs/e_u13b`). Worth a line in Known limits next to the other `ops_why_not` gaps.
5. Try-this field names that differ from the prose, found while running them: `update_track` takes `pickup` (not `pickups`), `directions` as a bitmask (3 for East/West, not names), `pool {"name": ..., "min_length": ...}` (a bare `min_length` is refused as unknown), `schedule: null` to remove a schedule, `load_options: []`; `setup_interchange` takes `destinations` as a plain list (`[]` for all); `set_active_day` takes `name`; `rename_location` takes `location` and `new`. The guide's prose is fine, but a reader copying field names will hit refusals.
6. R19 Try this cannot be run in the guide's order through the plugin: once allow_return is false, `ops_session update_car HZMX 9 passenger false` is refused ("This adds audit errors: Every track at West Staging that can depart holds a car with no destination on this train, so the build will fail. Turn A: HZMX 9 ...") and `ops_session` has no accept flag. The finding surfaces as that refusal, not from `ops_plan`. The JMRI result (TURN fails B20, "could not find destinations for 1 car(s) departing from staging track") was confirmed by editing the copy's XML (`runs/e_r19c_run`). Say "the change is refused with the staging-departure-blocked text; flip the passenger flag first, then allow_return".
7. The dry run keeps no state, so `ops_explain_build` on a copy after `ops_dry_run` reads the stale shipped report in `buildstatus/` (seen in U06, U12 and R14 checks). The guide's Try-this lines that quote `ops_explain_build` after a dry run need a real build (the session runner) first.
8. Session 2 and 3 facts that the guide could use: after three sessions LOCAL-H's cabooses alternate 1302, 1301, 1302; FIDDLE JOB's random line put JFN 801 alone on Fiddle South in `chain3` (the dry run earlier put 802 and 803 there), so any sentence naming which JFN 80x goes south is run-dependent.
