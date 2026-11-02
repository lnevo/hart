# Operations Pro showcase: guide

A tour of an invented railroad built to show what JMRI Operations Pro can do. Everything in it works. The cases are the setups that people on the user list found hardest, each shown done correctly, and every kind of routing the plugin's skill uses.

**Status: skeleton.** The text and the case list are settled. The `‹…›` marks in the "Find it" lines are names filled in when the database is built, by the showcase prompt ([`OPSPRO_SHOWCASE_PROMPT.md`](OPSPRO_SHOWCASE_PROMPT.md)). A `check_pointers` test makes sure each one points at something real.

## How to use it

1. Copy `examples/showcase/operations/` into a scratch JMRI profile, or open it with the plugin's reading tools. Nothing in it needs changing to work.
2. Pick a case. Cases are grouped: `U` for use-cases, `R` for routing.
3. For each case, read **The difficulty**, look at the objects under **Find it**, then use the tool named under **Confirm it** to see it working.
4. **Try this** is optional. It names one plugin action to run on a scratch copy that breaks the pattern, so you can see what the diagnosis says. The shipped folder is never in that state.

Every object a case uses has its code in its comment, for example `[U07]`. Search the Operations windows for the code.

| Heading | Meaning |
|---|---|
| The difficulty | What people found hard |
| How it's done here | The setup, in a few lines |
| Find it | Locations, tracks, schedules, trains and cars, by name |
| Confirm it | The tool, and what it should show |
| Try this | Optional break-it experiment, with the diagnosis it produces |

---

## Part 1: use-cases

### Loads and schedules

**U01. Industries that receive empties.** *Difficulty:* cars held with "can't send to spur due to load (E)". *How:* the spur's load options allow E, and the cars are of a type the spur takes. Find it: ‹…›. Confirm: `ops_why_not` shows the spur accepts the car (no E8). Try this: remove E from the spur's load option and watch gate E8 appear.

**U02. A schedule applied to a car already on a spur.** *Difficulty:* adding a schedule later seemed to do nothing. *How:* the schedule was applied by Set Car with "apply schedule", through `ops_deliver_car`. Find it: ‹…›. Confirm: the car carries the scheduled load and a final destination. Try this: add a schedule to a spur holding a car without delivering it; the audit shows `schedule-not-applied`.

**U03. Custom loads give cars a purpose.** *Difficulty:* default E and L cars wander. *How:* the shippers and receivers use custom loads and schedules; a few default cars are kept beside them to show the contrast. Find it: ‹…›. Confirm: custom-load cars reach their receiver; default cars do not.

**U04. A local move inside one location.** *Difficulty:* a car cannot move within a location. *How:* a custom load and a spur that demands it, in the same location. Find it: ‹…›. Confirm: the car ends on the demanding spur.

**U05. Move counts and priority.** *Difficulty:* priority did not make the car move. *How:* priority is used only to order analysis; Track Moves steer between tracks. Find it: ‹…›. Confirm: `ops_list` shows the counts. Try this: add a track and see the counts reset.

**U08. A fiddle yard of virtual spurs.** *Difficulty:* spreading traffic evenly. *How:* one virtual spur per destination area, each schedule line naming a downstream track; random and wait thin the rarer lines. Find it: ‹…›. Confirm: several sessions deliver across all the destinations.

**U09. One schedule for several spurs.** *How:* the same schedule on spurs with the same filters; nothing copied. Find it: ‹…›.

**U10. A mixed default and custom spur.** *How:* a second virtual spur named with `-(` so paperwork shows one spur. Find it: ‹…›.

### Staging

**U06. Departure staging with generated loads.** *Difficulty:* builds from staging failed. *How:* every car on the track can leave; custom loads are generated, including a track that holds only custom-load cars. Find it: ‹…›. Confirm: `ops_explain_build` shows each car assigned. Try this: remove the generated-load target and see gate C10.

**U07. Two staging tracks swapping full trains.** *How:* planned pick ups on the staging tracks. Find it: ‹…›. Confirm: both trains build in one session. Try this: clear the planned pick ups and see gate A7.

**U12. Normal and aggressive mode.** *How:* a staging train set up so it builds in both. Find it: ‹…›. Confirm: `ops_build_check` over several runs.

### Balance and sessions

**U11. Spurs and yards in balance.** *How:* route Moves, Max Length and schedules chosen so spurs refill and yards do not swell. Find it: ‹…›. Confirm: three sessions in a row keep the counts level.

**U14. Train schedule days.** *How:* a day is activated, then applied so the Build boxes follow. Find it: ‹…›. Confirm: the build report header shows the day. Try this: apply a different day and see gate A1.

**U15. An automation.** *How:* build, wait for terminate, terminate, in an order that is not the build order; no step opens a dialog. Find it: ‹…›. Confirm: `ops_live_automation`, or `ops_dry_run`.

**U16. Manual build lines.** Find it: ‹…›.

**U17. Paperwork.** *Difficulty:* lines overwritten, apostrophes and braces breaking text. *How:* manifest and switch list set apart, doubled apostrophes in messages. Find it: ‹…›. Confirm: `ops_list` type `manifest`.

**U20. On-time build order.** *How:* departure times in order, so a train may depart after the last one built. Find it: ‹…›.

### Equipment and special cars

**U13. Caboose, kernel, locomotive change, consist.** Find it: ‹…›. Confirm: the build carries each. Try this: split a kernel across two tracks; audit `kernel-split`.

**U18. Passenger blocking.** Find it: ‹…›.

**U19. Track pools.** Find it: ‹…›.

**U21. Divisions.** Find it: ‹…›.

**U22. Hazmat, buffer and idler cars, and other special cars.** Find it: ‹…›.

**U23. Backups.** *How:* an automatic backup set is present. Restore with `ops_backups` and `ops_restore` on a scratch copy. Find it: ‹…›.

---

## Part 2: routing variations

Each has a car whose route is the example. Use `ops_why_not` with the train named; its `router` field gives the route JMRI 5.16 would take.

| Code | Variation | How it's done | Find it |
|---|---|---|---|
| R01 | One train direct | The car's train reaches the spur | ‹…› |
| R02 | Two trains through an interchange | An interchange both trains serve | ‹…› |
| R03 | Two trains through a yard | Routing via yards on | ‹…› |
| R04 | Three or more trains | A chain through interchanges and yards | ‹…› |
| R05 | Through staging | Routing via staging on | ‹…› |
| R06 | Destinations filter as a gate | An interchange admitting chosen locations only | ‹…› |
| R07 | Pick ups by train and route | The same-route rule never traps a car | ‹…› |
| R08 | Routed option | On an interchange and on staging | ‹…› |
| R09 | Alternate and forward to yard | A full spur falls back | ‹…› |
| R10 | Overflow with a pool | A pool on a yard or interchange | ‹…› |
| R11 | A/D track with a switcher | Class tracks as interchanges; local interchange moves allowed | ‹…› |
| R12 | Local switcher | Spur to spur and yard to yard | ‹…› |
| R13 | Through-car rules | Origin to terminal off; all pick ups to terminal | ‹…› |
| R14 | Service all cars with a final destination | A train option that overrides the one-train rule | ‹…› |
| R15 | Directions | Masks that agree; direction as a filter | ‹…› |
| R16 | Hyphen names | One place on paper, two locations in use | ‹…› |
| R17 | Rest of the world | An interchange whose cars return loaded through a scheduled spur | ‹…› |
| R18 | Descriptive interchange | Not a physical track | ‹…› |
| R19 | Staging to staging | A turn | ‹…› |

---

## Known limits

Things the plugin does not yet do well, left out of the cases on purpose. ‹Filled in from `RESULTS.md`.›
