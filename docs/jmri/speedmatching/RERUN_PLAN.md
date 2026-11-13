# Plan: better speed-matching tools and a re-run of CSX 2121 and CSX 2738

Written 2026-11-12. Follows the first profile of 2026-11-08
([`profile-2026-11-08/README.md`](profile-2026-11-08/README.md)) and takes over what is useful
from the STRR club procedure ([`README.md`](README.md), the SOP PDF in `docs/ops/`).

## Goal

Measure 2121 and 2738 again with better tools: speeds over known block lengths, warmed-up
locos, both directions, the low steps, and a measured correction of 2738's table, written on
the main behind guardrails. The result is a speed profile for each loco that Dispatcher can use
for station stops, and a 2738 that matches 2121 in the consist as it runs.

## Decisions already made (owner, 2026-11-12)

- **Lengths come from the AnyRail plan, not a tape.** Blocks that are not in the `.any` plan get
  lengths inferred from the 2026-11-08 runs, based on the blocks the plan does have. That is a
  separate piece of work (Part A), and its output becomes the source of record.
- **Programming on the main is allowed**, with guardrails that make a broadcast command
  impossible (Part C).
- **No fixed target curve yet.** HART is not a club and does not need any loco to consist with
  any other. Profile the fleet first and decide on a target once the profiles are in.
- **2121 stays the reference for 2738.** The consist needs (2121 leads, 2738 reversed, same
  momentum) were already taken into account in the 2026-11-08 match. 2121's table is not
  changed.

## Part A: block lengths as a source of record (separate exercise)

Output: `jmri/layouts/hart/data/block_lengths.csv`, which is already the record for block
lengths (`docs/jmri/TRACK_LENGTHS.md`, `export_track_lengths.py`, checked by `./tools/check.sh`).
New `basis` values record where each length came from:

| basis | Meaning |
|---|---|
| `anyrail` | read from the AnyRail plan |
| `inferred` | worked out from timed runs against `anyrail` blocks (method below) |

1. **Plan file: 5.3b** (owner, 2026-11-12), in `~/Documents/Layout` (ADR-007).
2. **Read the `.any` file.** It is a binary Boost serialization archive, not XML. A first look
   (2026-11-12) found:
   - coordinates are doubles in **centimetres** (values such as 0.15875 = 1/16 in); the plan
     spans about 5.6 m by 8.1 m;
   - flex track (Peco code 83, `SL-8300`) is stored as cubic Bezier segments of four control
     points, so each length can be computed (997 segments found across all levels);
   - turnouts are Peco parts (`SL-8362`, `SL-8361`, `SL-8352`, `SL-8351`, `SL-8377`) placed by
     coordinates;
   - layers separate the levels and include `D.01` Mainline Track, `J.07.2` Power District Gaps
     and `D.07` Track Call Outs;
   - **there are no block names in the file**, and `jmri/layouts/hart/anyrail/hart.xml` is a
     rearranged panel (1837 by 558 units), not plan geometry, so it cannot link the two.

   The work left is to link pieces to HART blocks: build the track graph from piece endpoints,
   identify the turnouts, and match them to the turnouts in `tables.xml` by how they connect
   (the Layout Editor panel is not to scale, so position alone will not do). The Power District
   Gaps layer may mark some block ends. A rendered picture of the decoded main level, with
   turnout numbers, goes to the owner to confirm the matching. If the owner can export a format
   that names blocks or keeps the gaps, use it to shorten this.

   **Where the reader lives (owner, 2026-11-12):** the generic `.any` reader (pieces, lengths,
   layers, connections; no HART names) goes into the public `model-railroad-skills` plugin as
   an AnyRail skill with a tool and tests. It is built during Part A. Before it is published,
   check its lengths against what AnyRail itself shows for a few pieces, and label it in the
   plugin README as reverse-engineered and checked against AnyRail output, since AnyRail is
   closed source. The matching to HART's blocks stays in this repo.
3. **Map AnyRail blocks to HART blocks.** The `old_source` column (Yard Lead W, East Bypass and
   so on) already holds the AnyRail names.
4. **Infer the missing blocks.** The Switch 7 crossover and the engine terminal at Switch 13 may
   not be in the plan, and Main East and East Main Ext were `cut` by subtraction.
   `block_events.csv` holds 637 timed block transits for both locos at 11 steps. At one step
   the loco runs at one speed, so a block's length is its transit time multiplied by the speed
   measured on neighbouring `anyrail` blocks in the same lap. Use every step from 24 up (steady
   speed, no momentum effects), both locos, and record the median and spread. Prefer
   neighbours on level track, because grades change speed.
5. **Check it.** With the new lengths, re-run `block_speeds.py` on the 2026-11-08 logs. Each
   block's ratio to the loop mean should come out close to 1.00. The spread is the error bar
   for the record.
6. **Write the record.** Update the CSV with basis and a note per row, add the method to
   `docs/jmri/TRACK_LENGTHS.md`, regenerate, and bring the lengths into `tables.xml`. That
   changes tables, so it needs `./tools/check.sh`, `make panelpro-test` and a deploy. Dispatcher
   reads these lengths for stopping distances and shortest paths, so also say so in
   `wiki/STATUS.md`.

## Part B: tool changes

The runner and analysis scripts move out of the dated folder into a tools folder (proposed
`jmri/layouts/hart/scripts/speedmatch/`), with the 2026-11-08 folder kept as the record of that
run. They have no tests today, so tests come with the changes (AGENTS.md, "Working on existing
scripts").

1. **Warm-up.** A set number of laps (default 3) each way at a middle step before any
   measurement, logged and discarded. 2121 drifted 3 to 4% between runs at the top steps.
2. **Time over blocks, not laps.** Speed is a block transit over a known length, using only
   `anyrail` and `inferred` blocks from Part A. As in STRR, use fewer, longer spans at speed and
   every block at low speed. Report a rolling median and the standard deviation. Move to the
   next step when the deviation settles (default under 2%) or after a maximum number of
   readings. The low steps then take a few blocks instead of 10-minute laps.
3. **Direction as a setting.** Profile both directions. For the match, compare the two locos in
   the directions they run in the consist (2121 forward with 2738 reversed, and the other way
   round).
4. **More steps.** Add creep steps (2, 4, 6) and a repeat of step 126 at the end to measure
   drift.
5. **Decoder preflight.** Read and record CV2 to CV6, CV25, CV29, CV66, CV67 to CV94, CV95 and the
   back-EMF CVs before each run, and stop if they differ from the roster. Settle back-EMF before
   matching. Note the known decoder traps: Digitrax CV57 limits the lowest speed, and some TCS
   decoders stall at table values of 250 and up.
6. **Measured correction.** `propose_table.py` currently assumes table entry k acts at step
   126k/28 and writes the table once. The new step: after the write, measure each anchor step
   again, adjust that entry by the measured error, write it on the main (Part C), and repeat
   until every anchor is within tolerance (default ±3%, about the top-end repeatability) or a
   maximum number of rounds is reached.
7. **Tests.** Unit tests for block selection, the median and stop rule, length inference
   (Part A) and the table correction, run on the 2026-11-08 data. No hardware and no MQTT in
   tests.

## Part C: programming on the main, with guardrails

Built: `jmri/layouts/hart/scripts/speedmatch/pom_guard.py` and `pom_write.py`; what it refuses
and how to run, apply and roll back are in [`POM_GUARD.md`](POM_GUARD.md).

Over LCC, JMRI sends an addressed CV write to the CS-105's train node for one DCC address
(`OlcbProgrammer`, JMRI 5.16). A DCC broadcast is address 0. The guard is one small module that
every write goes through:

1. **Address from the roster only.** The programmer comes from the roster entry's address and
   long or short flag, never from typed input. Refuse address 0, refuse a short address outside
   1 to 127, refuse if the flag does not match the roster, and refuse if another roster entry
   shares the address.
2. **No consist in the path.** 2121 leads an LCC consist with 2738. Refuse to write while either
   loco is in an active consist; the consist is broken first and made again afterwards with
   `cs105_consist.py`. Never write to a consist address.
3. **Allowed CVs only:** 3, 4, 25, 29, 66, 67 to 94, 95. CV29 changes only bit 4 (speed table)
   and keeps the bits it read. Never CV1, CV17 to 19 (addresses and consist) or CV8 (reset).
4. **Dry run by default.** It prints every write (address, CV, old value, new value). Writing
   needs an explicit `--apply`. Each run saves a rollback file of the values it read.
5. **No power or stop-all.** The tools stop a loco with its own throttle at speed 0, never with
   emergency stop on every loco or track power.
6. **Check after writing.** Without RailCom a write on the main cannot be read back, so the check
   is the re-measure. At the end, read the full table back on the programming track and update
   the roster (the Pi is the master; sync the Mac and Windows).
7. **Tests:** the refusals (address 0, wrong flag, shared address, consist, CV outside the
   list) are tested in-process with a fake programmer.

## Part D: re-run 2121 and 2738

Before starting: Part A at least for the loop blocks, Parts B and C merged, PanelPro running on
the Pi, and the owner not operating. Only the test loco moves.

1. Preflight both decoders (Part B.5) and save the CVs.
2. **2121:** warm up, then profile both directions with the new step list. No changes to its
   decoder.
3. **2738:** warm up, then profile both directions. Compare with 2121 in the consist pairing.
4. If any anchor is outside tolerance, correct 2738's table on the main (B.6, Part C) and
   measure again.
5. Make the consist again and repeat the stop test from 2026-11-08 at steps 32 and 96, to
   confirm momentum still matches.
6. Write the measured profiles into each roster entry's speed profile, which Dispatcher uses,
   then sync the roster.
7. Record the results in a new dated folder next to `profile-2026-11-08/`, and update
   `wiki/projects/speedmatching.md` and `wiki/STATUS.md`.

## Not in this plan

- A fleet target curve: decided after more locos are profiled.
- The other 15 roster locos: they follow with the same tools once this run is done.
- The STRR scripts themselves: their hardware (Digitrax, BDL168) does not match HART's.

## Open questions for the owner

- Is ±3% the right tolerance for 2738 against 2121? Undecided; revisit once the new profiles
  show the spread between runs.

The stop test, where both locos held full speed for about 6 s after the speed-0 command, is a
separate investigation (owner, 2026-11-12) and is not part of this plan.
