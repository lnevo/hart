# Prompt: build the Operations Pro showcase railroad

Give this to a Claude Code session with the `operations-pro` plugin loaded (`external/model-railroad-skills/plugins/operations-pro`, branch `agent/claude/operations-pro`). It builds one invented railroad, in working order, that shows each Operations Pro feature and every kind of routing the skill can use. The companion guide is [`OPSPRO_SHOWCASE_GUIDE.md`](OPSPRO_SHOWCASE_GUIDE.md); the build must make every pointer in it true.

This is a plugin deliverable, not a HART one. The plugin is public and generic. Paste everything under the line.

---

## Task

Build a showcase Operations folder: an invented railroad with no connection to any real layout, and finish the guide that walks a reader through it.

**The railroad is not broken.** Every train builds, every car goes where the design intends, and the audit has nothing to report. The cases are the things people on the user list found hard to set up, shown here set up correctly, so a reader can open the database and see how it is done.

The reader should be able to:

1. Pick a use-case from the guide and find the exact locations, tracks, schedules, trains and cars that do it.
2. Build the railroad in real JMRI and watch it behave as the guide says.
3. Copy the pattern into their own railroad.

## Hard rules

- **Generic only.** No HART content, no real railroad, person or company names, and no forum member names or thread links. Invent the railroad, towns, industries and roads. Run the plugin's banned-terms test as the plugin's own instructions say (`OPS_BANNED_TERMS=hart`).
- **Working order.** Every shipped state builds cleanly in real headless JMRI 5.16. `ops_audit` returns no findings. If a pattern needs a setting the audit flags (for example a deliberate virtual spur), either find the form that does not trip it or list it in the guide as an intended finding, with the reason.
- **Every claim is checked.** What a case does must be what real headless JMRI 5.16 does. Assert it in a test: the named car ends at the named track, the named train carries the named cars. If a pattern does not behave as the research says, drop or reword it and say so. Never keep a case because the research asserts it.
- **Use the plugin, not hand edits.** Build through `ops_plan` and `ops_apply`. A hand edit is allowed only where the plugin has no action; list each with the reason. The known exclusions are in SKILL.md (a car's final destination, adding a car to a built train, train build and terminate scripts, track type change).
- **Leave out what the plugin gets wrong.** Where the research recorded a FAIL or PARTIAL scenario that is still open (for example a permanent custom load lost on arrival in staging), do not build a case for it; list it under "Known limits" in the guide.
- **Keep the plugin as it is.** If a case needs a plugin change, stop and report it.
- **Do not touch the HART Operations data, `tables.xml`, PanelPro or CATS.**

## Sources

Read the skill first (`skills/operations-pro/SKILL.md` and all nine references; `routing.md`, `staging.md`, `loads-and-schedules.md` and `build-order.md` matter most). Then read the research the skill came from, in `media/hart-research/opspro/` (gitignored; local only):

- `situations.md`: the 27 situation families seen on the user list.
- `digest.md`, `digest2.md`: numbered lessons.
- `verification.md`: each lesson checked against JMRI 5.16 source. It is the authority; where it disagrees with the digests, it wins.
- `scenarios/g1` to `g5`: 49 real problems rebuilt and run in real JMRI. Each problem is a use-case someone struggled to set up. Use the PASS ones. A PARTIAL one qualifies only if the working part stands alone.

Paraphrase. Carry over no names of posters and no thread addresses.

The existing test railroad at `tests/fixtures/demo/operations/` (Brackwater, Ashgrove, Tolvern) is for the test suite and has deliberate faults. **Do not edit it.** The showcase is a new, separate folder, `examples/showcase/operations/`, with different names.

## What to build

A railroad of about 12 locations, 16 trains and 100 cars, in two layers. Both layers live in the one database and share its map; each case still gets its own location or track so a pointer is a single name.

### Layer 1: the use-cases people struggled with, working

One case per use-case, code `U01` onward. Cover at least these, adding more where the research shows a passing scenario:

| Code | Use-case |
|---|---|
| U01 | Industries that receive empties, with the load options set so they accept them |
| U02 | A schedule applied to a car already on a spur (the Set Car "apply schedule" route) |
| U03 | Custom loads that give cars a purpose, beside default E and L cars that wander |
| U04 | A local move inside one location, done with a custom load and a demanding spur |
| U05 | Track move counts used to prefer one track; priority used for what it is for |
| U06 | Departure staging with generated custom loads, including all-custom staging |
| U07 | Two staging tracks swapping full trains, with planned pick ups |
| U08 | A fiddle yard of virtual spurs, with schedule lines naming downstream tracks; random and wait columns thin the rarer lines |
| U09 | One schedule shared by several spurs |
| U10 | A mixed default and custom spur through a second virtual spur named with "-(" |
| U11 | Spurs and yards in balance: route Moves, Max Length and schedules |
| U12 | A staging train that builds in both normal and aggressive mode |
| U13 | Equipment: a caboose, a kernel, a locomotive change at a stop, a consist |
| U14 | Train schedule days: Activate and Apply for each day; the Build boxes follow |
| U15 | An automation that builds, waits for terminate, and terminates in a chosen order; no dialog steps |
| U16 | Manual build lines |
| U17 | Paperwork set away from the defaults: manifest and switch list lines, phrases with doubled apostrophes, colours |
| U18 | A passenger train with blocking order |
| U19 | Track pools with minimum and maximum length |
| U20 | On-time build order with departure times |
| U21 | Divisions with home-division routing |
| U22 | Hazmat, buffer and idler cars, and any of LCL, icing, RIP, unit trains or TOFC the skill covers |
| U23 | Backups: an automatic backup set exists, and the guide shows the restore |

### Layer 2: every routing variation the skill uses

One case per variation, code `R01` onward. Each has a car whose route is the example. Include at least:

| Code | Routing variation |
|---|---|
| R01 | One train direct to a spur |
| R02 | Two trains through an interchange |
| R03 | Two trains through a yard (routing via yards on) |
| R04 | A chain of three or more trains through interchanges and yards |
| R05 | A route through staging (routing via staging on) |
| R06 | An interchange whose Destinations filter admits only chosen locations, as a gate |
| R07 | Pick ups named by train and by route on an interchange, so the same-route rule never traps a car |
| R08 | The Routed option on an interchange and on staging |
| R09 | A spur with an alternate, and forward to yard on a full destination |
| R10 | Overflow on a yard or interchange handled by a pool |
| R11 | An A/D track with a yard switcher, the class tracks as interchanges, and local interchange moves allowed |
| R12 | A local switcher working spur to spur and yard to yard |
| R13 | Through-car rules: origin to terminal off; send all pick ups to terminal |
| R14 | "Service all cars with a final destination" on a train |
| R15 | Directions: location, track and stop masks that agree, and a direction used as a filter |
| R16 | Hyphen-named locations that print as one place and work as two |
| R17 | A rest-of-the-world interchange whose cars come back loaded through a scheduled spur |
| R18 | A descriptive (non-physical) interchange |
| R19 | A staging-to-staging turn |

For every case, tag each object it uses with its code: the location, train, route and car comments start with `[U07]` or `[R04]`, and so on. This is the pointer scheme the guide relies on.

### What each case must carry

1. The objects, built through the plugin.
2. An **expected result**, written as a test: after the build (and, where it matters, a second session), these cars are on these tracks and these trains carried them. Where randomness applies, run enough builds to show the result holds, using `ops_build_check`.
3. The tool that confirms it: which of `ops_why_not` (its `router` field for routing cases), `ops_explain_build` or `ops_list` shows the working result, with the gate id or field. Record what it says.
4. An optional **experiment**: one plugin action, to be applied on a scratch copy only, that breaks the pattern. Run it once, record which tool names the cause and the gate id, and put it in the guide as "Try this". The shipped folder never contains the broken state.

## Work split

Run stages as separate sessions; each ends by writing a file the next starts from.

| Stage | Work | Model |
|---|---|---|
| 1. Plan | Read the skill and research. Settle the railroad's name and map, the full case list with its expected result per case, and which locations each case uses. Write `examples/showcase/PLAN.md`. Stop for approval. | The strongest available (Fable 5.1, else Opus 5.5) |
| 2. Skeleton | Build the shared map: locations, tracks, routes, car types, roads, base cars. Prove it builds clean. | Sonnet 5.5 |
| 3. Cases, in batches of about six | Build the objects, write the expected-result tests, prove them in real JMRI. One session per batch, each starting from `PLAN.md` and its case rows. Batches touch different locations, so they can run in parallel on separate copies and be merged. | Sonnet 5.5 |
| 4. Integrate | Merge the batches, run the whole railroad through several sessions, clear any audit finding, finish the guide and make every pointer resolve. | Sonnet 5.5 |
| 5. Review | An independent read of every behavioural claim against JMRI 5.16 source (Java file and line, or a failing test). | A fresh session on the strongest model, shown only the guide and the database, not this prompt's conclusions |

Token rules: pass each stage the files it needs by path; use `ops-diagnoser` for long build reports; keep plans small. Cases that share a map must be integrated before sessions are run together, because a car served by two cases is a conflict, not a feature.

## Deliverables (in the plugin, on its branch)

- `examples/showcase/operations/`: the six Operations XML files, with the active day set and a `buildstatus` folder holding a report from a clean build, so the guide can quote it without running JMRI.
- `examples/showcase/GUIDE.md`: the finished guide (start from `docs/ops/OPSPRO_SHOWCASE_GUIDE.md` in the HART repo and fill in the pointers).
- `examples/showcase/PLAN.md` and `RESULTS.md` (per case: expected result, the test that proves it, the tool that confirms it, runs, and the experiment's outcome).
- A `check_pointers` test that fails if a guide pointer names an object not in the database.
- Plugin tests pass; a test that the showcase loads and saves unchanged in real JMRI where it is installed (skips otherwise), and one that `ops_audit` returns nothing.
- A list of every hand edit and every case dropped or reworded, with the reason.

Stop after stage 1 and wait for approval before building.
