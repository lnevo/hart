# Speed-match tools

Measure how fast a loco runs at each throttle step, compare two locos in the directions they
run in the consist, and work out a corrected speed table. Built for the re-run of CSX 2121 and
CSX 2738 (Part D of [`RERUN_PLAN.md`](../../../../../docs/jmri/speedmatching/RERUN_PLAN.md)).
The 2026-11-08 run and its scripts stay as the record in
[`docs/jmri/speedmatching/profile-2026-11-08/`](../../../../../docs/jmri/speedmatching/profile-2026-11-08/).

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
| `jython/step_runner.py` | warm-up, then the step profile | Pi, inside JMRI |
| `jython/move_to.py` | runs a loco until a named sensor lights, then stops it (positioning) | Pi, inside JMRI |
| `preflight_compare.py` | compares a preflight log with the roster entry | Mac |
| `analyze.py` | turns step logs into speeds, drift and the 2121/2738 comparison | Mac |
| `correct.py` | proposes a corrected table (CV67 to CV94) | Mac |
| `liverule.py` | the stop rule and span arithmetic, used by both the runner and the analysis | both |

`liverule.py` is written so it also runs under Jython 2.7. `make_job.py` pastes it in front of
`step_runner.py`, so the runner on the Pi runs the same code the tests check (there is no second
copy to drift).

Tests: `jmri/layouts/hart/scripts/tests/test_speedmatch.py` (run by `./tools/check.sh`).

## How a measurement works

- **Warm-up first.** The loco runs 3 laps (setting) at step 64 (setting) before any
  measurement. The log marks them `WARMUP`; the analysis throws them away.
- **Speed over blocks, not laps.** Speed is the time from lighting one block sensor to lighting
  the sensor of the block after it (or after 3 blocks at higher steps), over the length of the
  blocks entered. Steps up to 48 use every block; higher steps use spans of 3 blocks.
  The first 2 sensor events after a step change are thrown away (the loco is still changing
  speed).
- **Lengths** come from `jmri/layouts/hart/data/block_lengths.csv`. Only trusted rows count:
  with a `basis` column, `anyrail` and `inferred`; without one, `flag` = `assigned`. Blocks
  without a trusted length are skipped, so until Part A lands only a few blocks qualify.
  `make_job.py` refuses to build a job if none do. Change the set with `--trusted`.
- **Stop rule.** A step ends when the last 5 readings differ by under 2% (relative standard
  deviation), or after 12 readings, or after 15 minutes. The reported speed is the median of
  those last 5 readings. A creep step (6 or lower) that stops moving is logged and skipped.
- **Direction is a setting** (`forward` or `reverse` on the throttle). Results are keyed by
  loco and direction. The analysis also reads which way round the loop the loco went (`east` or
  `west`) from the order the sensors lit, and the comparison flags a pair that did not travel
  the same way.
- **Steps:** 2, 4, 6, 8, 12, 16, 24, 32, 48, 64, 80, 96, 112, 126, then 126 again. The analysis
  reports how far the second 126 differs from the first (top-step drift).

## Running it (Part D), step by step

Before you start: PanelPro on the Pi is running (so `jmri_cmd_watcher` is up), you are not
operating, the test loco is on the track, and the tracks and turnouts are lined for the loop
by hand. Only the test loco moves. Use a scratch folder, for example `/tmp/sm`.

All commands run from the repo root on the Mac. Set `export HART_PI_SSH=pi` if your ssh name
for the Pi differs.

### 1. Preflight (the loco alone on the programming track)

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

It lists every CV that differs from the roster and exits 1 if any differ or any read failed.
**Stop if it says DIFFERENT**; sort out which is right before measuring. `--save` keeps what
was read, which is also the rollback record. CV list: CV2 to CV6, CV25, CV29, CV66, CV67 to
CV94, CV95, plus the back-EMF CVs of the decoder family (`--backemf`: `tsunami2` = 209 to 213,
`tcs` = 49, 56, 57; check the manual for any other decoder). Known traps: Digitrax CV57 limits
the lowest speed, and some TCS decoders stall at table values of 250 and up.

### 2. Step profile, one loco, one direction

Put the loco on the loop, lights on. Then, for example 2121 forward:

```bash
python3 jmri/layouts/hart/scripts/speedmatch/make_job.py steps --loco "CSX 2121" \
    --direction forward --mute-sound --guard "BS W-1" --guard "BS W-2" --out /tmp/sm/steps_2121_fwd.py
jmri/layouts/hart/scripts/speedmatch/drop_job.sh /tmp/sm/steps_2121_fwd.py
```

The job prints `started`. Watch the log on the Pi (`ssh pi tail -f /tmp/steprun_...log`);
lines are `WARMUP_LAP`, `STEP n`, `READ ...`, `STEPDONE n reason=settled|max|time|stalled`.
To stop early: `drop_job.sh --kill` (the runner sets its own throttle to 0 and ends; afterwards
remove the flag yourself: `ssh pi rm /tmp/speedrun.kill`). A runner holds `/tmp/speedrun.active`
while it runs and `drop_job.sh` refuses a new runner job until it is gone (`--force` only after
the log shows END). It also
ends on its own if a guard sensor lights, or no sensor changes for 120 s (shown as `STOP`).
A guard sensor can be any sensor (user or system name); the job refuses to start if one is
not found or is already lit. The no-event limit follows a settled step's pace but never goes
above `--stall-cap` (300 s), and a step that stalled never raises it. To position a loco
first: `make_job.py move --loco "CSX 2738" --direction reverse --step 24 --until "BS Switch 33"
--guard "BS W-1" --out /tmp/sm/move.py`, then `drop_job.sh` it (it stops at speed 0 when the
sensor has been lit for 0.8 s, after 90 s, or on the kill flag).
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
  step 126 is labelled `126#2`.
- `drift.csv`: the second 126 against the first, in percent.
- `compare.csv`: 2738 against 2121 for the two consist pairings, 2121 forward against 2738
  reverse, and 2121 reverse against 2738 forward (`b_vs_a_pct` is 2738 relative to 2121).
  `same_travel` says whether both went the same way round the loop.

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
tolerance, 2 proposal written, 3 out of rounds (default 5). Each entry is scaled by target
speed over measured speed, at most 1.5 times per round, limited to 1 to 255 and never
decreasing from one entry to the next. Entry k is taken to act at step 126 x k / 28; speeds at
those (fractional) steps are interpolated from the measured steps.

The proposal is **not applied**. It goes to the write guard (dry run first, then `--apply`),
then re-run steps 2 and 3 for the corrected loco in the chosen direction, and `correct.py` with
`--round 2` and the table you wrote. Repeat until it exits 0 or reaches the round limit.
The speed table is the same in both directions, so after it is within tolerance in one
pairing, check the other pairing in `compare.csv`. Anchors outside the measured steps are left
unchanged and reported as having no usable measurement; entries left alone keep their value.

## Known limits

- The back-EMF CV lists in `make_job.py` come from the CVs present in the 2121 and 2738 roster
  entries. A different decoder needs its own list from the manual.
- The service-mode read uses JMRI's global programmer. If the Pi's JMRI has none set, the log
  says `NO PROGRAMMER` and nothing is read.
- The Jython runner and preflight have only been checked as text and for syntax shape in tests;
  the first real run on the Pi is their first run in JMRI. Try `--steps 24 --warm-laps 0`
  first.
