# Prompt: build the Operations Pro showcase railroad

Give this to a Claude Code session with the `operations-pro` plugin loaded (`external/model-railroad-skills/plugins/operations-pro`, branch `agent/claude/operations-pro`). It builds an invented railroad whose database shows each Operations Pro feature and reproduces the common problems people hit, each with its fix. The companion guide is [`OPSPRO_SHOWCASE_GUIDE.md`](OPSPRO_SHOWCASE_GUIDE.md); the build must make every pointer in it true.

This is a plugin deliverable, not a HART one. The plugin is public and generic. Paste everything under the line.

---

## Task

Build a showcase Operations folder, an invented railroad with no connection to any real layout, and finish the guide that walks a reader through it.

The reader should be able to:

1. Open the railroad in JMRI and see every major feature at work.
2. Meet each common problem in a place built to show it, run the plugin's diagnosis on it, and see the cause named.
3. Apply the fix and see the build succeed.

## Hard rules

- **Generic only.** No HART content, no real railroad, person or company names, and no forum member names or thread links. Invent the railroad, towns, industries and roads. Run the plugin's banned-terms test as the plugin's own instructions say (`OPS_BANNED_TERMS=hart`).
- **Every claim is checked.** The behaviour each case shows must be the behaviour real headless JMRI 5.16 produces. If a case does not behave as the research says, drop or reword it and say so. Never keep a case because the research asserts it.
- **Use the plugin, not hand edits.** Build through `ops_plan` and `ops_apply`. A hand edit is allowed only where the plugin has no action, and each one is listed in the report with the reason. The known exclusions are in SKILL.md (a car's final destination, adding a car to a built train, train build and terminate scripts, track type change).
- **Do not demonstrate what the plugin gets wrong.** Where the research recorded a FAIL or PARTIAL scenario that is still open (for example a permanent custom load lost on arrival in staging), leave it out of the cases and list it under "Known limits" in the guide.
- **Keep the plugin as it is.** If a case needs a plugin change, stop and report it. Do not change the plugin to make a demo work.
- **Do not touch the HART Operations data, `tables.xml`, PanelPro or CATS.**

## Sources

Read the skill first (`skills/operations-pro/SKILL.md` and all nine references). Then, for evidence and wording, read the research the skill came from, in `media/hart-research/opspro/` (gitignored; local only):

- `situations.md`: the 27 situation families seen on the user list.
- `digest.md`, `digest2.md`: numbered lessons.
- `verification.md`: each lesson checked against JMRI 5.16 source. It is the authority; where it disagrees with the digests, it wins.
- `scenarios/g1` to `g5`: 49 real problems rebuilt and run in real JMRI, with verdicts. Use the PASS ones as the case list; PARTIAL ones only if the passing part stands alone.

Paraphrase. Carry over no names of posters and no thread addresses.

The existing test railroad at `tests/fixtures/demo/operations/` (Brackwater, Ashgrove, Tolvern) is for the test suite. **Do not edit it.** The showcase is a new, separate folder: `examples/showcase/operations/`. You may borrow ideas from it, but build the showcase fresh, and keep the names different.

## What to build

### Part A: a working railroad that shows the features

A railroad that builds cleanly with no faults, small enough to read in a sitting (about 8 locations, 12 trains, 60 cars) and covering, each at least once:

- Locations and divisions; spur, yard, interchange and staging tracks; track directions; Pick ups and Set outs lists.
- Car types, roads, default loads and custom loads; kernels.
- Industry schedules: match and sequential, random, wait, hits.
- Routes with several stops; a multi-train route through an interchange; the router choosing a path.
- Staging that sends and receives, with generated loads and a swap between two staging tracks.
- Locomotives: models, a consist, a change at a stop; a caboose; a passenger train with blocking order.
- Track pools; train schedule days with the Build boxes applied for a day; manual build lines; an automation that builds, waits for terminate and terminates in a chosen order.
- Manifest and switch list formats set away from the defaults.

### Part B: the problem rooms

One **case** per common problem, each built in its own location (so a pointer is a single location name), each with a **broken** state and the **fix** that cures it. Use this catalogue, adjusting only where a check proves a case wrong:

| Code | Problem shown |
|---|---|
| I01 | A spur refuses an empty: its load option excludes E |
| I02 | A schedule added to a spur does nothing to a car already parked there |
| I03 | A track's Destinations filter strips the schedule's track, so cars scatter across the yard |
| I04 | Route direction and location direction disagree, so the train never works the stop |
| I05 | A car cannot make a local move inside one location; the hyphen name that splits a place in two |
| I06 | Default E and L cars wander with no purpose; custom loads give them one |
| I07 | Priority does not guarantee a move; track move counts steer; adding a track resets them |
| I08 | A build from staging fails because one car cannot leave |
| I09 | Staging with only custom loads fails when a car gets no generated load |
| I10 | Two full trains need to swap between two staging tracks |
| I11 | A turn sets a car out on an interchange and never picks it up (same-route rule) |
| I12 | An interchange's Destinations "accept only X" is a gate, not an attraction |
| I13 | Overflow from one interchange: an alternate is refused; a pool cures it |
| I14 | Spurs drain and yards fill: route Moves, Max Length and schedules |
| I15 | A build that succeeds in normal mode and fails in aggressive |
| I16 | A caboose, a locomotive or a kernel that blocks a build |
| I17 | Nothing builds: the wrong day is active or Apply cleared the Build boxes |
| I18 | A new train takes nothing: it is missing from the tracks' lists |
| I19 | A build that stalls on a dialog on the JMRI computer |
| I20 | Edits that vanish because JMRI was running; recovery from the automatic backup |
| I21 | Trains that finish in a different order from the one they were built in |
| I22 | Paperwork: switch list lines overwritten by "same as manifest", a lone apostrophe in a message, an unmatched brace |
| I23 | Passenger blocking order |
| I24 | A pool with a minimum length that no train can meet |
| I25 | On-time build order: a train may not depart before the last one built |

For each case:

1. Build the broken state.
2. Show the plugin finds it: record which of `ops_audit`, `ops_why_not` or `ops_explain_build` names the cause, and its gate id or finding name. If none do, mark the case "not detected" and say so in the guide.
3. Apply the fix as a plugin action (or the smallest set of them).
4. Prove the fix in real headless JMRI: `ops_build_check` or `ops_dry_run`, several runs where randomness applies. Record before and after.

Tag every object a case uses with its code: the location comment starts with `[I07]`, and so do the train, route and car comments that belong to it. This is the pointer scheme the guide relies on.

## Work split

Run stages as separate sessions; each ends by writing a file the next starts from.

| Stage | Work | Model |
|---|---|---|
| 1. Plan | Read the skill and research. Settle the railroad's name, map, and the case list with a one-line check for each. Write `examples/showcase/PLAN.md`. Stop for approval. | The strongest available (Fable 5.1, else Opus 5.5) |
| 2. Part A | Build and prove the clean railroad. | Sonnet 5.5 |
| 3. Part B, in batches of about five cases | Build, diagnose, fix, prove. One session per batch, each starting from `PLAN.md` and the case rows. | Sonnet 5.5, one per batch; batches are independent, so they can run in parallel on separate copies of the folder and be merged by location |
| 4. Guide and pointers | Finish the guide, make every pointer resolve, run the pointer check. | Sonnet 5.5 |
| 5. Review | An independent read of every behavioural claim against JMRI 5.16 source (Java file and line, or a failing test). | A fresh session on the strongest model, shown only the guide and the database, not this prompt's conclusions |

Token rules: pass each stage the files it needs by path; use `ops-diagnoser` for long build reports; keep plans small.

## Deliverables (in the plugin, on its branch)

- `examples/showcase/operations/`: the six Operations XML files, plus a `buildstatus` folder holding the broken-state report for each case so the guide can quote it without running JMRI.
- `examples/showcase/GUIDE.md`: the finished guide (start from `docs/ops/OPSPRO_SHOWCASE_GUIDE.md` in the HART repo and fill in the pointers).
- `examples/showcase/PLAN.md`, `RESULTS.md` (per case: detected by which tool and gate, before, after, runs), and a `check_pointers` test that fails if a guide pointer names an object that is not in the database.
- Plugin tests pass; add a test that the showcase loads and saves unchanged in real JMRI where it is installed, and skips otherwise.
- A short list of every hand edit and every case dropped or reworded, with the reason.

Stop after stage 1 and wait for approval before building.
