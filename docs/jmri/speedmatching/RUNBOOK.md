# Speed-match runbook

The tools live in [`jmri/layouts/hart/scripts/speedmatch/`](../../../jmri/layouts/hart/scripts/speedmatch/). Paths below are from the repo root.

Measure how fast a loco runs at each throttle step, compare two locos in the directions they
run in the consist, and work out a corrected speed table. Built for the re-run of CSX 2121 and
CSX 2738 (Part D of [`RERUN_PLAN.md`](RERUN_PLAN.md)).
The 2026-11-08 run and its scripts stay as the record in
[`docs/jmri/speedmatching/profile-2026-11-08/`](profile-2026-11-08/).

These tools **never write to a decoder**. The runner moves one loco with its own throttle and
stops it with that throttle at speed 0 (no emergency stop, no track power, no turnouts). The
preflight only reads CVs. The correction only proposes a table. Writing is a separate guard
module (`pom_guard.py`, built elsewhere).

## What is here

| File | What it does | Where it runs |
|---|---|---|
| `make_job.py` | builds a job file (settings, then the runner) | Mac |
| `drop_job.sh` | copies a job to the Pi's `jmri_cmd_watcher`, fetches logs, sets the kill flag | Mac |
| `jython/preflight.py` | reads CVs on the programming track | Pi, inside JMRI |
| `jython/jobkit.py` | what the three movers share (throttle, sensors, guards, the active marker, the end of a run); pasted in front of each | Pi, inside JMRI |
| `jython/step_runner.py` | warm-up, then the step profile (laps mode, the default) | Pi, inside JMRI |
| `jython/distance_runner.py` | distance mode: warm-up in seconds, then one continuous pass through the steps, each measured over a distance | Pi, inside JMRI |
| `jython/pass_runner.py` | one timed pass through a stretch of loop 2, for placing Switch 7 and Switch 13 | Pi, inside JMRI |
| `jython/move_to.py` | runs a loco until a named sensor lights, then stops it (positioning) | Pi, inside JMRI |
| `jython/stop_test.py` | starts a loco from rest, sends speed 0 when a sensor lights, logs every sensor event | Pi, inside JMRI |
| `stoptest_compare.py` | two stop-test logs into one table (seconds after the command, resting block) | Mac |
| `profile_to_roster.py` | `profile.csv` into the payload for the roster profile writer | Mac |
| `jython/write_profile.py` | writes measured speeds into a roster entry's speed profile (dry run unless told) | Pi, inside JMRI |
| `preflight_compare.py` | compares a preflight log with the roster entry | Mac |
| `analyze.py` | turns step logs into speeds, drift and the 2121/2738 comparison | Mac |
| `correct.py` | proposes a corrected table (CV67 to CV94) | Mac |
| `liverule.py` | the stop rule, span arithmetic, settle time, block readings and the distance end rule, used by the runners and the analysis | both |

`liverule.py` is written so it also runs under Jython 2.7. `make_job.py` pastes it in front of
`step_runner.py`, so the runner on the Pi runs the same code the tests check (there is no second
copy to drift).

Tests: `jmri/layouts/hart/scripts/tests/test_speedmatch*.py` (run by `./tools/check.sh`). The distance and
pass runners are also run for real, as Python 3 on a virtual clock with a fake loco
(`test_speedmatch_distance.py`), which checks the log order, the stop, the guard and the kill
flag. They have still not run in JMRI.

To watch a run from the Mac while it happens, start the live page: [`DASHBOARD.md`](DASHBOARD.md).

## How a measurement works

- **Warm-up first.** The loco runs 3 laps (setting) at step 64 (setting) before any
  measurement. The log marks them `WARMUP`; the analysis throws them away.
- **Speed over blocks, not laps.** Speed is the time from lighting one block sensor to lighting
  the sensor of the block after it (or after 3 blocks at higher steps), over the length of the
  blocks entered. Steps up to 48 use every block; higher steps use spans of 3 blocks.
  The first 2 sensor events after a step change are thrown away (the loco is still changing
  speed).
- **Lengths** come from `jmri/layouts/hart/data/block_lengths.csv`. Only trusted rows count:
  `anyrail` and `inferred`, read from the `basis` column or, when the file has none, from the
  `flag` column. `assigned` counts only if you pass it with `--trusted`. Blocks
  without a trusted length are skipped, so until Part A lands only a few blocks qualify.
  `make_job.py` refuses to build a job if none do. Change the set with `--trusted`.
- **Stop rule.** A step ends when the last 5 readings differ by under 2% (relative standard
  deviation), or after 12 readings, or after 15 minutes. The reported speed is the median of
  those last 5 readings. A creep step (6 or lower) that stops moving is logged and skipped.
- **Direction is a setting** (`forward` or `reverse` on the throttle). Results are keyed by
  loco and direction. The analysis also reads which way round the loop the loco went (`east` or
  `west`) from the order the sensors lit, and the comparison flags a pair that did not travel
  the same way.
- **Steps (laps mode):** 2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 80, 96, 112, 126, then 126 again. The analysis
  reports how far the second 126 differs from the first (top-step drift).

## The 40-minute layout procedure

The whole layout job in one sitting: both locos in both directions, then Switch 13. It uses
**distance mode** (below) for the profiles and the **pass job** for Switch 13. PanelPro is
running on the Pi, the owner is not operating, only the test loco moves. Times are estimates
from the 2026-11-08 speeds (corrected for the longer loop); the first real run replaces them.

| Part | What | Minutes |
|---|---|---|
| 1 | Break the 2121/2738 consist (`cs105_consist.py` detach), line up loop 1 (`make_job.py lineup --route loop1`), build the four jobs | 5 |
| 2 | **2121 forward**: warm 60 s, then the distance pass. Its first two steps (8 and 16) are the shakedown: watch the log live (`ssh pi tail -f`), check `STEP`, `SETTLE`, `MEASURE`, `BLOCK` and the sensor order, and `drop_job.sh --kill` if anything looks wrong | 6 |
| 3 | **2121 reverse**: `--warm-s 0` (already warm), same job | 5 |
| 4 | Swap to 2738 (no `--mute-sound`), then **2738 forward** with its 60 s warm-up | 9 |
| 5 | **2738 reverse**, `--warm-s 0` | 6 |
| 6 | Loop 2: line up (`make_job.py lineup --route loop2`), position a loco (`move`), then **two passes through Switch 5 to Switch 15** at steps 24 and 48 | 8 |
| 7 | Fetch the logs, `analyze.py`, `infer_block_lengths.py --locate --pass-log` | 1 |
| | Total | about 40 |

Steps per pass: 8, 16, 24, 32, 48, 64, 96, 126. A pass is about 4.5 minutes for 2121 and 6 for
2738 (their low steps take the full 60 s of measuring, the high ones about 13 s). One log per
pass; every command below runs from the repo root, with `/tmp/sm` as the scratch folder.

```bash
MJ=jmri/layouts/hart/scripts/speedmatch/make_job.py
DJ=jmri/layouts/hart/scripts/speedmatch/drop_job.sh
# part 2 and 3: 2121 (a fresh job each time: the log name carries the time)
python3 $MJ steps --loco "CSX 2121" --direction forward --mode distance --mute-sound --guard default --out /tmp/sm/d_2121_f.py
python3 $MJ steps --loco "CSX 2121" --direction reverse --mode distance --mute-sound --warm-s 0 --guard default --out /tmp/sm/d_2121_r.py
# part 4 and 5: 2738
python3 $MJ steps --loco "CSX 2738" --direction forward --mode distance --guard default --out /tmp/sm/d_2738_f.py
python3 $MJ steps --loco "CSX 2738" --direction reverse --mode distance --warm-s 0 --guard default --out /tmp/sm/d_2738_r.py
$DJ /tmp/sm/d_2121_f.py        # wait for END in the log, fetch it, then the next
```

Each pass sets the loco's own throttle to 0 at the end. Between passes drop the next job only
after the log shows `END` (the runner holds `/tmp/speedrun.active`). After reversing, the loco
simply runs the other way round the loop from where it stopped.

Part 6, Switch 13. Line up loop 2, then put a loco two blocks behind Switch 5 on the route, so it
is at speed when it reaches the first pin (`BS Switch 1`, then Brick-Plane, then Switch 5; pick
the throttle direction that runs it that way):

```bash
python3 $MJ lineup --route loop2
python3 $MJ move --loco "CSX 2121" --direction forward --step 24 --until "BS Switch 1" --route loop2 --guard default --out /tmp/sm/m.py
python3 $MJ pass --loco "CSX 2121" --direction forward --step 24 --from "BS Switch 5" --to "BS Switch 15" \
    --route loop2 --guard default --out /tmp/sm/pass24.py       # then again with --step 48
```

Do the step 24 pass, bring the loco back round to Switch 1 with `move`, and do step 48. Then:

```bash
python3 jmri/layouts/hart/scripts/infer_block_lengths.py --route loop2 --locate \
    --pass-log /tmp/sm/pass_*_step24_*.log /tmp/sm/pass_*_step48_*.log
```

It reports each pass (speed between the pins, then OS Switch 7 and OS Switch 13 centres in mm
from Switch 5's points and in mm before OS Switch 15's centre), then the mean of the passes and how far
they differ. A large difference between step 24 and step 48 means the loco was still speeding up at
Switch 5: repeat with the loco further back. Use the mean as the placement.

## Running it (Part D), step by step

Before you start: PanelPro on the Pi is running (so `jmri_cmd_watcher` is up), you are not
operating, the test loco is on the track, and the tracks and turnouts are lined for the loop
by hand. Only the test loco moves. Use a scratch folder, for example `/tmp/sm`.

All commands run from the repo root on the Mac. Set `export HART_PI_SSH=pi` if your ssh name
for the Pi differs.

### 1. Preflight (the loco alone on the programming track) - optional

The preflight is optional when the roster entry comes from a full DecoderPro read on the
programming track. That is true for CSX 2121 and CSX 2738 as of 2026-11-13. Then skip this step;
the first guarded CV write (step 4) needs `ROSTER_OLD_OK = True` instead of a preflight record
(see "Apply settings" below). Run it when the roster entry has been edited by hand since the
last read, or for any other loco.

HART has no RailCom, so CVs cannot be read on the main. The preflight uses the programming
track (service mode), so this is a separate step before the loco goes to the loop. Put the
loco on the programming track, then:

```bash
mkdir -p /tmp/sm
python3 jmri/layouts/hart/scripts/speedmatch/make_job.py preflight --loco "CSX 2738" \
    --backemf tcs --out /tmp/sm/pre_2738.py          # --backemf tsunami2 for CSX 2121
jmri/layouts/hart/scripts/speedmatch/drop_job.sh /tmp/sm/pre_2738.py
```

It prints the log name on the Pi (`/tmp/preflight_CSX_2738_<time>.log`). Reading about 45 CVs
takes a few minutes. Wait for the line `END`, then:

```bash
jmri/layouts/hart/scripts/speedmatch/drop_job.sh --fetch /tmp/preflight_CSX_2738_<time>.log /tmp/sm
python3 jmri/layouts/hart/scripts/speedmatch/preflight_compare.py \
    --log /tmp/sm/preflight_CSX_2738_<time>.log \
    --roster-xml ~/JMRI_UserFiles/roster/2738.xml --save /tmp/sm/cvs_2738.json
```

It lists every CV that differs from the roster and exits 1 if any differ or any read failed,
if the log has no END line or has an ERROR or ABORTED line, or if an expected CV is missing
(it names them).
**Stop if it says DIFFERENT**; sort out which is right before measuring. `--save` keeps what
was read, which is also the rollback record. CV list: CV2 to CV6, CV25, CV29, CV66, CV67 to
CV94, CV95, plus the back-EMF CVs of the decoder family (`--backemf`: `tsunami2` = 209 to 213,
`tcs` = 49, 56, 57; check the manual for any other decoder). Known traps: Digitrax CV57 limits
the lowest speed, and some TCS decoders stall at table values of 250 and up.

### 2. Step profile, one loco, one direction

Put the loco on the loop, lights on. Then, for example 2121 forward:

```bash
python3 jmri/layouts/hart/scripts/speedmatch/make_job.py steps --loco "CSX 2121" \
    --direction forward --mute-sound --guard default --out /tmp/sm/steps_2121_fwd.py
jmri/layouts/hart/scripts/speedmatch/drop_job.sh /tmp/sm/steps_2121_fwd.py
```

The job prints `started`. Watch the log on the Pi (`ssh pi tail -f /tmp/steprun_...log`);
lines are `WARMUP_LAP`, `STEP n`, `READ ...`, `STEPDONE n reason=settled|max|time|stalled`.
To stop early: `drop_job.sh --kill` (the runner sets its own throttle to 0 and ends; afterwards
remove the flag yourself: `ssh pi rm /tmp/speedrun.kill`). A runner holds `/tmp/speedrun.active`
while it runs and `drop_job.sh` refuses a new runner job until it is gone (`--force` only after
the log shows END). It also
ends on its own if a guard sensor lights, or no sensor changes for 120 s (shown as `STOP`).
`--guard` is required for `steps`, `move` and `stoptest`: name the sensors that must abort a
run, or pass `--guard none` to run without one on purpose (the log then says `NO GUARD`).
`--guard default` stands for every block sensor in `tables.xml` that is not on the job's route
(`--route loop1`, the default, or `loop2`; it can be combined with more names). The list is
computed from `tables.xml` for the route (`guard_for()` in `make_job.py`), so a new block sensor is
guarded at once; the tests check it per route. A loco leaving the route for any of them ends the
run. **Not covered yet:** the McKees
Rocks and McKeesport stubs. Their detector sections are not on a node yet
(`wiki/STATUS.md`, 2026-11-13) and the tables still give them only the combined
`BS Switch 39 / BS McKees Rocks` and `BS Switch 37 / BS McKeesport` sensors, which are loop
sensors, so they cannot be guarded until the stub sections go live and get their own sensors.
Until then keep the turnouts at Switches 37 and 39 lined for the loop. Steps are whole numbers 1 to 126; anything else is
refused. Every job (steps, move and preflight) holds `/tmp/speedrun.active`, so none starts
while another is running.
A guard sensor can be any sensor (user or system name); the job refuses to start if one is
not found or is already lit. The no-event limit follows a settled step's pace but never goes
above `--stall-cap` (300 s), and a step that stalled never raises it. To position a loco
first: `make_job.py move --loco "CSX 2738" --direction reverse --step 24 --until "BS Switch 33"
--guard default --out /tmp/sm/move.py`, then `drop_job.sh` it (it stops at speed 0 when the
sensor has been lit for 0.8 s, after 90 s, or on the kill flag).
Sound: `--mute-sound` switches F8 on, which is 2121's mute (Tsunami2 diesel, sound). CSX 2738
needs no mute: its roster entry (`~/JMRI_UserFiles/roster/2738.xml`) has decoder family "MC Motor
Decoders", model MC2H104P9, a TCS motor decoder without sound, so leave `--mute-sound` off for it.
Every job (`steps`, `move`, `stoptest`) takes `--route loop1|loop2` (default loop1); a steps
job logs it in the CFG line, and `analyze.py` replays each run over the route it logged
(`--route` there is only the fallback for logs without one). `correct.py --route` reads only
that route's runs from `profile.csv`. `make_job.py lineup --route loop2` prints the switch
positions to set by hand; nothing is ever sent.
Flags worth knowing: `--steps 24,48,126`, `--warm-laps 3`, `--warm-step 64`, `--rel 0.02`,
`--max 12`, `--stall 120`. Run all four combinations: 2121 forward, 2121 reverse, 2738
forward, 2738 reverse, each from a fresh `make_job.py` (the log name carries the time).

When a log ends with `END`, fetch it: `drop_job.sh --fetch /tmp/steprun_<...>.log /tmp/sm`.

### 3. Analysis and the consist comparison

```bash
python3 jmri/layouts/hart/scripts/speedmatch/analyze.py /tmp/sm/steprun_*.log --out /tmp/sm/out
```

Writes in `/tmp/sm/out`:

- `profile.csv`: per loco, direction and step the median speed (mm/s), relative standard
  deviation, readings used, and why the step ended (`settled`, `max`, `open`). A repeat of
  step 126 is labelled `126#2`. Every run in the logs gets its own `run` number (the same loco
  and direction twice are two runs, never merged), with `run_complete` and the log name.
- `drift.csv`: within one run, the second 126 against the first, in percent.
- `compare.csv`: 2738 against 2121 for the two consist pairings, 2121 forward against 2738
  reverse, and 2121 reverse against 2738 forward (`b_vs_a_pct` is 2738 relative to 2121).
  `same_travel` says whether both went the same way round the loop. It uses the latest
  complete run of each loco and direction.

The analysis replays each run with the stop-rule settings and block lengths the runner logged
(`CFG`, `LENGTHS`). `--csv-lengths` swaps in the current CSV lengths only; the logged
stop-rule settings still apply.

Block lengths currently trusted are printed on the first line. If few blocks are trusted the
readings are few and slow to settle; that is the data telling you Part A is not finished.

### 4. Correct a table (only after the profiles are in)

Profile both locos in both directions first (step 2). Then the owner chooses which pairing
to correct against (which loco's profile is the target, in which direction) and the tolerance
(`--tol`, default 0.03 is only a placeholder). Nothing here assumes either choice: `--direction`
and `--target-direction` have no default. The example below is only the shape of the command.

```bash
python3 jmri/layouts/hart/scripts/speedmatch/correct.py \
    --roster-xml ~/JMRI_UserFiles/roster/2738.xml \
    --profile /tmp/sm/out/profile.csv --loco "CSX 2738" --direction reverse \
    --target-loco "CSX 2121" --target-direction forward \
    --round 1 --out /tmp/sm/round1
```

(Use `--table v1,...,v28` instead of `--roster-xml` after the first round, taking the values
you actually wrote.) It prints each table entry whose speed is outside the tolerance and the new value,
and writes `proposal.json` and `proposal.csv` in the output folder. Exit status: 0 all within
tolerance, 2 proposal written, 3 for out of rounds (default 5), blocked (a cut cannot be made
because of the rising table) or stuck (no entry can change). Only a proposal with status
`continue` has `writes`; the others keep the details in `changes` and `proposal.csv`. Each entry is scaled by target
speed over measured speed, at most 1.5 times per round, limited to 1 to 255 and never
decreasing from one entry to the next. Entry k is taken to act at step 126 x k / 28; speeds at
those (fractional) steps are interpolated from the measured steps.

The proposal is **not applied**. It goes to the write guard (dry run first, then `--apply`),
then re-run steps 2 and 3 for the corrected loco in the chosen direction, and `correct.py` with
`--round 2` and the table you wrote. Repeat until it exits 0 or reaches the round limit.
The speed table is the same in both directions, so after it is within tolerance in one
pairing, check the other pairing in `compare.csv`. Anchors outside the measured steps are left
unchanged and reported as having no usable measurement; entries left alone keep their value.

`correct.py` reads the latest complete run of each loco and direction from `profile.csv`;
`--run N` and `--target-run N` pick another. A cut an entry needs is never undone by the
rising rule: the entries before it that were within tolerance are pulled down with it. If one
of them is itself out of tolerance the cut is blocked, the status is `blocked` and the exit
status 3; the entries are named in `proposal.json` (`blocked_cvs`).

### 5. Stop test (after the tables match, and again after the consist is remade)

Repeats the 2026-11-08 momentum test. The loco starts from rest in the loop, runs at one step,
and when the trigger sensor lights it gets speed 0 from its own throttle (no emergency stop).
Every sensor event is logged with a time stamp, then logging goes on for 30 s after the command,
or until 10 s pass without an event. Position the loco first with `make_job.py move`, then for
each loco in turn (the same start block, direction and step for both):

```bash
python3 jmri/layouts/hart/scripts/speedmatch/make_job.py stoptest --loco "CSX 2738" \
    --direction forward --step 96 --trigger "BS Switch 33" --guard default --out /tmp/sm/stop_2738.py
jmri/layouts/hart/scripts/speedmatch/drop_job.sh /tmp/sm/stop_2738.py
```

The log is `/tmp/stoptest_<loco>_<direction>_<time>.log` on the Pi; wait for `END`, fetch it, and
make the table from the two logs:

```bash
python3 jmri/layouts/hart/scripts/speedmatch/stoptest_compare.py /tmp/sm/stoptest_CSX_2738_*.log \
    /tmp/sm/stoptest_CSX_2121_*.log --out /tmp/sm/stoptest.md
```

It lists the seconds after the stop command at which each sensor lit and the block each loco
came to rest in (the trigger's own lighting is left out). The 2026-11-08 result at step 96 was
both within 0.1 s at every sensor, both at rest in K-2. Options: `--settle-s 30`, `--quiet-s 10`,
`--max-s 180` (longest run before the trigger), `--mute-sound`. The trigger is a loop sensor given by its user name (system names are refused). It only acts once the loco has been sent off; if it is already lit then, the run ends with speed 0 and no measurement. The job holds
`/tmp/speedrun.active`, honours the kill flag, and refuses to start if the trigger or a guard
is lit or missing, or if the trigger is also a guard.

**Consist:** a consist is driven through its lead only. To test the made consist, give the roster
id of the lead loco as `--loco` (the CS-105 moves the followers); the log is one log for the
whole consist, so compare it with a single-loco log or with a second consist run, not
loco against loco.

### 6. Write the profile into the roster (Dispatcher)

Dispatcher reads each roster entry's speed profile. CSX 2121 and CSX 2738 still carry the
synthetic one (10 points, 400 mm/s at the top). When both locos are final, per loco:

```bash
python3 jmri/layouts/hart/scripts/speedmatch/profile_to_roster.py /tmp/sm/out/profile.csv \
    --loco "CSX 2121" --out /tmp/sm/payload_2121.json
python3 jmri/layouts/hart/scripts/speedmatch/make_job.py profile --payload /tmp/sm/payload_2121.json \
    --out /tmp/sm/profile_2121.py
jmri/layouts/hart/scripts/speedmatch/drop_job.sh /tmp/sm/profile_2121.py
```

`profile_to_roster.py` takes the latest complete run per loco and direction and only the steps
that ended `settled` (the repeat `126#2` is skipped). A step needs a speed in both directions to
become a point; the others are listed as left out. It refuses if either direction has no complete
run or no settled step. The job is a **dry run**: it logs the old and the new profile
(`OLD`/`NEW` lines) and changes nothing. Read the log, then build it again with `--apply` and
drop that. The apply clears the entry's profile, sets the points (key = step / 126 x 1000,
speeds in mm/s, as in JMRI 5.16 `RosterSpeedProfile`), saves the roster entry and the roster
index, and logs the profile read back (`STOP written`). It touches no throttle, power, turnout
or CV, and holds `/tmp/speedrun.active` like the other jobs.

**The Pi is the roster master.** The write happens in the Pi's JMRI. Afterwards sync the roster
to the Mac and Windows with `tools/hosts/sync_roster_from_pi.sh`; do not edit the roster on
another host in between.

## Distance mode

`make_job.py steps --mode distance` is the quick form of the step profile. Laps mode (the default,
above) is unchanged. Distance mode makes one continuous pass: warm-up for a time, then every
step in order without stopping, then speed 0 with the loco's own throttle. It has the same guards,
kill flag, stall limit and active marker (all from `jobkit.py`). No laps are counted.

- **Steps** default to `8,16,24,32,48,64,96,126` (`--steps`, still whole numbers 1 to 126).
- **Warm-up** `--warm-s 60 --warm-step 48`, in seconds (0 = none).
- **Settle** after each step change, momentum plus a margin:
  `settle_s = 0.896 x CV3 x |step change| / 126 + 2` going up, with CV4 in place of CV3 going down.
  `--cv3` and `--cv4` default to 26 and 24 (the roster values of both locos) and are logged. The
  runner logs `SETTLE`, waits, and measuring starts at the next `ACTIVE` of a route sensor.
- **Measuring.** A block is read when it was crossed whole: entry of block k to entry of block
  k+1, both on the route, in travel order, with a trusted length. A missed sensor restarts the
  chain. A step ends when the crossed blocks add up to `--target-mm` (6000) over at least
  `--min-blocks` (2) blocks (reason `settled`), or after `--max-s` (60) seconds of measuring. The
  speed is sum(mm) / sum(seconds). A step that ran out of time still counts when it has at least
  `--min-blocks` blocks whose speeds spread no more than `--rel` (reason `timed`, used like
  `settled`); with fewer blocks or more spread it is `max` and not used. `stalled` is not used.
- **Spread.** If the single-block speeds at that point spread more than `--rel` (0.03) and another
  `--target-mm` still fits in the time left, the step takes one more reading of that length once
  (logged as `EXTRA`) and the speed is over all the blocks.
- **Stall.** No route sensor event for `--stall` seconds (120, following the pace of settled
  steps up to `--stall-cap`) ends the run; a stall at or below `--stall-skip-below` (6) only skips
  that step. A stalled step logs `STEPDONE ... reason=stalled`.

`analyze.py` replays a distance log the same way (it reads `CFG mode=distance`, the logged
distance settings, and the sensor events from `MEASURE` on, through the same `liverule.py`
classes) into `profile.csv`: one row per step, speed in `median_mm_s`, `readings` = blocks, `settled`
when the step ended `settled` or `timed`. `profile_to_roster.py` and `correct.py` take those rows
(both reasons); a `max` or `stalled` step is left out of the roster profile.

## The pass job

`make_job.py pass` runs one timed pass through a stretch of a route and logs every sensor event,
to place OS Switch 7 and OS Switch 13 from times:

```bash
python3 $MJ pass --loco "CSX 2121" --direction forward --step 24 --from "BS Switch 5" --to "BS Switch 15" \
    --route loop2 --guard default --out /tmp/sm/pass24.py
```

The loco starts from rest at `--step` (position it a couple of blocks behind `--from` so it is at
speed there), and is stopped with its own throttle once `--to` has lit and then the sensor one
block further on (BS S-R for Switch 15) has lit, or after `--max-s` (240 s), a stall (`--stall`,
120 s), the kill flag or a guard. `--from`, `--to` and that last sensor are refused if they are
not on the route or are also guards. `infer_block_lengths.py --route loop2 --locate --pass-log LOG
[LOG ...]` places the two centres between the Switch 5 and Switch 15 pins: speed is taken as
constant between them, the centre of a section is halfway between its entry and the entry of the
next section in travel, and the pins' centres sit at their plan positions (140 and 5909 mm from
Switch 5's points). Each pass is reported, then the mean and the spread.

## Log lines

Every line is `<epoch seconds with 3 decimals> <message>`. The live dashboard reads exactly these;
key=value pairs have no spaces in their values (spaces in names become underscores, as in `mid=`).

```
RUN loco=<roster id> direction=<forward|reverse>
CFG route=<r> mode=distance steps=<a,b,..> target_mm=<n> min_blocks=<n> max_s=<n> rel=<r> warm_s=<n> warm_step=<n> cv3=<n> cv4=<n> mid=<...>
LENGTHS <json {sensor user name: mm}>
WARMUP <step> secs=<n>
WARMUP_DONE
STEP <n>
SETTLE <n> secs=<s>
MEASURE <n> from=<sensor user name>
SENS <sensor user name> <ACTIVE|INACTIVE|UNKNOWN|INCONSISTENT>
BLOCK <step> block=<sensor_user_name_with_underscores> mm=<len> dt=<s> mm_s=<v>
FREEZE <n>
STEPDONE <n> reason=<settled|timed|max|stalled> n=<blocks> mm=<sum> s=<sum> mm_s=<v> relsd=<r>
PATH <sensor>,<sensor>,...
PASS step=<n> from=<sensor> to=<sensor>
PASSDONE reason=<..>
STOP <why>
END
```

- Distance mode logs, per step: `STEP`, `SETTLE`, `MEASURE`, then `SENS` and `BLOCK` lines, then
  `FREEZE`, then `STEPDONE`. `FREEZE <n>` is the moment the runner stops taking blocks (before
  the totals are worked out); a `SENS` line between `FREEZE` and `STEPDONE`, or between `STEP`
  and `MEASURE`, is not measured, and the analysis counts events only from `MEASURE` to
  `FREEZE`. `SENS` lines are logged for every block sensor and guard, in the order events were
  fed; the `RUN` and `LENGTHS` lines are as in laps mode (laps mode's `CFG`, `WARMUP n laps=`,
  `WARMUP_LAP`, `READ` and `STEPDONE ... median=` lines are unchanged).
- Also logged, outside the dashboard's contract: `EXTRA <n> relsd=<r>` when a step takes its one
  extra reading, `NO GUARD`, and the end of run lines `speed 0`, `F<n> off`, `throttle released`,
  `ERROR <..>`.
- The pass job logs `RUN`, `CFG route=<r> mode=pass step=<n> max_s=<n>`, `PATH`, `PASS`, `SENS`,
  `PASSDONE reason=<passed|max|stalled|killed|guard_<name>|..>`, then `STOP` and `END`. In `PASS`,
  `from=` and `to=` are the sensor user names as they are (spaces kept). `PATH` is the sensors
  expected from `from` to `to`, the shorter way round the route, user names as they are,
  comma separated, logged just before `PASS`. A route sensor that is not on it lighting after
  `from` and before `to` stops the pass at once (`PASSDONE reason=wrong_way`, `STOP wrong way`).
  `infer_block_lengths.py` refuses a pass whose sensors did not light in the `PATH` order, and a
  pass whose `from` and `to` are not both pins of the route's plan (it names the pins). `analyze.py`
  skips a log whose `CFG` says `mode=pass`.
- `MEASURE ... from=` is the user name as it is (spaces kept); only `BLOCK ... block=` and `mid=`
  use underscores.
- `STEPDONE ... n=0` (and `mm=0.0 s=0.00 mm_s=0.0 relsd=0.0000`) when a step took no readings.
- A run is complete when it ends `STOP all steps complete`.

## Loop 2 (S-R, Scale, Barn): placing Switch 13

Loop 1 placed Switch 7b on the AnyRail plan. A second timed loop does the same for OS Switch 13
and the Scale side of OS Switch 7, which sit between Switch 5 and Switch 15. Loop 2 runs
Switch 5 (thrown) into Track Scale, Switch 7, Track Barn, Switch 13, Switch 15 and Track S-R,
then Switch 23b, 31 and 33, and on as loop 1 from East Lead to Brick-Plane and back to Switch 5.

Line the switches up by hand (`make_job.py lineup --route loop2` prints this; the tools never
command turnouts):

| Switch | Position | | Switch | Position |
|---|---|---|---|---|
| 5 | thrown | | 31 | closed |
| 7 | closed | | 33 | closed |
| 13 | closed | | 35 | closed |
| 15 | closed | | 37 | thrown |
| 23 | closed | | 39 | thrown |
| 1 | thrown | | | |

(Loop 1 is 5 closed, 7 closed, 33 thrown, 35 closed, 37 thrown, 39 thrown, 23 closed, 1 thrown.)
The guard for loop 2 includes BS Main East, BS East Ext and BS Switch 7b, which loop 1 runs
over.

The quick way is the pass job above (two passes at steps 24 and 48). The lap survey below
gives the same placement plus the lengths of Scale, Barn, S-R, OS 23b and OS 31.

Survey run, one loco and direction, at least 3 laps per step (the first lap of each step is
dropped, so allow one more):

```bash
python3 jmri/layouts/hart/scripts/speedmatch/make_job.py steps --loco "CSX 2121" \
    --direction forward --mute-sound --route loop2 --steps 32,48,64 --warm-laps 1 \
    --guard default --out /tmp/sm/steps_loop2.py
jmri/layouts/hart/scripts/speedmatch/drop_job.sh /tmp/sm/steps_loop2.py
```

Fetch the log, then turn it into lap events and place the switches (steps from 24 up are used):

```bash
python3 jmri/layouts/hart/scripts/speedmatch/analyze.py /tmp/sm/steprun_*.log --out /tmp/sm/out \
    --route loop2 --events-out /tmp/sm/loop2_events.csv
python3 jmri/layouts/hart/scripts/infer_block_lengths.py --route loop2 \
    --events /tmp/sm/loop2_events.csv --locate
```

A lap is one pass of all 22 sensors counted from BS Switch 5; a block's transit is its entry to
the next sensor's entry, and a block whose next sensor was missed gets no row (that lap is not
used). The report lists every block's length pinned to the plan turnouts (Switch 5, 15, 33, 35a,
35b, 23a, 1; 23b and 31 are left unpinned on purpose, too close to 33), then
`locate:` lines giving the centre of OS Switch 7 and OS Switch 13 in mm along the route from
Switch 5's points, and how far each is before OS Switch 15's centre. That distance is where the
switch goes on the plan. It also prints loop 1's value beside loop 2's for the 14 rows both routes
cover, as a consistency check; a large gap means a bad run or a wrong pin.

`--apply` writes only rows loop 1 did not set (Scale, Barn, S-R, OS 7, 13, 15, 23b, 31); add
`--overwrite` to rewrite the 17 loop 1 rows as well. Like loop 1, apply with PanelPro and CATS
closed, then run `export_track_lengths.py`.

Not yet checked on the layout: the lineup, the loop 2 plan constants against a real run, and the
sensor order on a physical pass (the first run is the check).

## Apply settings (writing CVs, `pom_write.py`)

The write guard ([`POM_GUARD.md`](POM_GUARD.md)) is dry run first. The apply run needs these
settings in the job, and each is logged:

- `ROSTER_OLD_OK = True` - lets the guard take the roster's CV values as the old values when no
  preflight record exists. Needed for the first guarded apply of CSX 2121 and CSX 2738, whose
  roster came from a full DecoderPro read on the programming track (2026-11-13), so step 1 can
  be skipped.
- `CONSISTS_BROKEN = True` - your confirmation that every consist involving the loco is
  detached. For 2121 and 2738 detach the LCC consist first with `cs105_consist.py`, then set it.
- `ABSENT_OK = [...]` - roster ids whose train node is not on the CS-105 that day (the guard
  asks every roster loco's node to answer). Build the list from a consist query: any roster loco
  the query shows as absent goes in. The target loco itself can never be in it.

## Known limits

- The back-EMF CV lists in `make_job.py` come from the CVs present in the 2121 and 2738 roster
  entries. A different decoder needs its own list from the manual.
- The service-mode read uses JMRI's global programmer. If the Pi's JMRI has none set, the log
  says `NO PROGRAMMER` and nothing is read.
- The Jython runners and preflight have only been checked as text and for syntax shape in tests
  (the distance and pass runners also run in a simulation, as Python 3); the first real run on the
  Pi is their first run in JMRI. Use the first two steps of the first pass as the shakedown, or
  try `--mode distance --steps 24 --warm-s 0` first.
- Distance mode needs at least two trusted blocks in a row on the route; a route with few trusted
  lengths gives steps that end on time with few or no blocks.
