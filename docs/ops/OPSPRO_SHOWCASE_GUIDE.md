# Operations Pro showcase: guide

A walk through an invented railroad built to show what JMRI Operations Pro can do, and the problems people most often meet with it. Every problem sits in a room of its own, broken, with the fix beside it.

**Status: skeleton.** The text and the cases are settled. The names in the "Find it" lines are filled in when the database is built, by the showcase prompt ([`OPSPRO_SHOWCASE_PROMPT.md`](OPSPRO_SHOWCASE_PROMPT.md)). A `check_pointers` test makes sure each one points at something real. Until then, treat `‹…›` as not yet filled.

## How to use it

1. Copy `examples/showcase/operations/` to a scratch folder. Never run the broken cases against a railroad you care about.
2. Close JMRI. File edits and the plugin's write actions need JMRI exited.
3. Work through Part A to see the features, then pick any case in Part B.
4. For each case: read **What you'll see**, look at the objects in **Find it**, run the tool named under **Diagnose**, apply the **Fix**, then rebuild.

Every object a case uses has its code in its comment, for example `[I07]`. Search the Operations window for the code.

## Reading a case

| Heading | Meaning |
|---|---|
| What you'll see | The symptom a person reports |
| Find it | Location, track, train, route and cars in the database, by name |
| Why | The rule in JMRI that causes it (checked against 5.16) |
| Diagnose | Which plugin tool names the cause, and the gate id or finding it returns |
| Fix | The plugin action that cures it |
| Prove it | What the build shows afterward |

---

## Part A: the working railroad

The clean railroad builds with no warnings. Open it first.

| Feature | Find it | Look for |
|---|---|---|
| Locations and divisions | ‹locations› | Division on each location; track types |
| Spurs, yards, interchange, staging | ‹tracks› | Type on each track; directions; Pick ups and Set outs lists |
| Loads | ‹car types› | The default E and L, and the custom loads |
| Schedules | ‹industries› | Match and sequential; random, wait and hits columns |
| Routes and the router | ‹route, interchange› | A car crossing two trains through an interchange |
| Staging | ‹staging tracks› | Generated loads; a swap between two staging tracks |
| Locomotives, consists, caboose | ‹engines, trains› | A change at a stop; the caboose rule |
| Passenger blocking | ‹passenger train› | Blocking order on the manifest |
| Pools | ‹pooled tracks› | Minimum and maximum length |
| Days | ‹train schedule› | The active day and each train's Build box |
| Manual build lines | ‹train› | The line and its action (warn, fail or remove) |
| Automation | ‹automation› | Build, wait for terminate, terminate, in order |
| Paperwork | ‹manifest settings› | Non-default prefixes, phrases and colours |

---

## Part B: the problems

### Cars that will not move

**I01. A spur refuses an empty.** *Seen as:* "Can't send to spur due to load (E)".
Find it: ‹location, spur, car›. Why: the spur's Load Option does not allow the default empty. Diagnose: `ops_explain_build` and `ops_why_not`, gate E8. Fix: allow E on the spur, or give the car a custom empty the schedule asks for.

**I02. A schedule added later does nothing to the car already there.** Find it: ‹…›. Why: a schedule applies when a car is delivered, so a car already parked is untouched. Diagnose: audit finding `schedule-not-applied`. Fix: `ops_deliver_car`, which acts as Set Car with "apply schedule".

**I03. Cars scatter across the yard.** Find it: ‹…›. Why: a track's Destinations filter excludes the track the schedule names. Diagnose: audit `interchange-no-exit`; `ops_why_not` to the spur. Fix: set the filter to accept all, or add the spur's location.

**I04. The train never works the stop.** Find it: ‹…›. Why: the route direction and the location's train directions do not overlap. Diagnose: the route notes in `ops_explain_build`. Fix: set the location or the route direction.

**I05. A car will not do a local move.** Find it: ‹…›. Why: a default load cannot move within one location; a hyphenated name prints as one place but is two locations. Diagnose: `ops_why_not`, gate D4. Fix: use a custom load and a demanding spur, or a final destination.

**I06. Default E and L cars wander.** Find it: ‹…›. Why: nothing points a default load anywhere; only custom loads are routed. Fix: a custom load with a schedule that asks for it.

**I07. Priority did not make the car move.** Find it: ‹…›. Why: priority only sets the order of analysis. To prefer one track, change Track Moves. Adding a track or schedule resets the counts. Fix: `set_track_moves` after the change.

### Staging

**I08. A build from staging fails.** Find it: ‹…›. Why: every car on the departure track must leave, and one cannot (type, load, length, out of service). Diagnose: `ops_why_not` for each car; gate B20 is a consequence, not the cause. Fix: the setting the stuck car's story names.

**I09. All-custom staging fails.** Find it: ‹…›. Why: a car gets no generated load. Diagnose: gates C10 and the plan warning `generator-no-target`. Fix: ship-empties option or a generator target.

**I10. Two trains swap between two staging tracks.** Find it: ‹…›. Why: staging takes cars only if the track is empty. Diagnose: gate A7. Fix: planned pick ups on the staging tracks (see `build-order.md`).

### Interchanges and routing

**I11. A turn sets out a car and never picks it up.** Find it: ‹…›. Why: Pick ups "Any" with the same-route rule. Diagnose: gate B6. Fix: name the pulling train or route in Pick ups.

**I12. "Accept only X" is a gate, not an attraction.** Find it: ‹…›. Why: the filter limits next location and final destination; it does not pull cars. Fix: a custom load and a schedule.

**I13. Overflow from an interchange.** Find it: ‹…›. Why: an alternate cannot be set on an interchange. Fix: a pool.

### Moves and balance

**I14. Spurs drain and yards fill.** Find it: ‹…›. Why: length limits reached early, no schedules, yard counts low. See `moves-and-balance.md`. Fix: raise route Moves and Max Length; add schedules.

**I15. Builds in normal mode, fails in aggressive.** Find it: ‹…›. Why: in aggressive mode the departure-staging adjustment runs only on the first pass. Diagnose: the first-pass lines in the report. Fix: see the diagnosis reference. Compare several builds, since staging picks are random.

### Equipment

**I16. A caboose, locomotive or kernel blocks the build.** Find it: ‹…›. Diagnose: audit `caboose-road-mismatch`, `engine-no-train`, `kernel-split`. Fix: the setting each names.

### Days, trains and files

**I17. Nothing builds.** Find it: ‹…›. Why: the wrong day is active, or Apply cleared the Build boxes. Diagnose: the report header and gate A1. Fix: `set_active_day`, then `apply_day`.

**I18. A new train takes nothing.** Find it: ‹…›. Why: it is missing from the tracks' Pick ups and Set outs. Diagnose: audit `train-not-on-list`. Fix: `add_train` writes the lists.

**I19. A remote build never finishes.** Find it: ‹…›. Why: a dialog is open on the JMRI computer. Fix: `ops_train` turns dialogs off for the build.

**I20. Edits vanished.** Why: made while JMRI ran, then overwritten at autosave or exit. Fix: `ops_restore` from the automatic backup; redo with JMRI exited.

### Sessions and paperwork

**I21. Trains finish in a different order from the build order.** Find it: ‹…›. Why: terminate is independent per train; cars a train frees are available only to trains built after it terminates. Fix: an automation with wait-for-terminate steps.

**I22. Paperwork that prints wrongly.** Find it: ‹…›. Why: "same as manifest" rewrites the switch list lines on save; a lone apostrophe or an unmatched brace breaks message text. Fix: `set_manifest_options`, `set_manifest_text` with doubled apostrophes.

**I23. Passenger blocking.** Find it: ‹…›. Why: blocking order and the passenger flag decide the manifest order. See the blocking reference.

**I24. A pool no train can meet.** Find it: ‹…›. Why: the pool minimum exceeds what any train can carry. Diagnose: the pool-minimum audit finding. Fix: lower the minimum.

**I25. A train may not depart before the last one built.** Find it: ‹…›. Why: on-time build order. Fix: correct the departure times or turn on-time mode off.

---

## Known limits

Things the plugin does not yet do well, left out of the cases on purpose. ‹Filled in from `RESULTS.md`.›
