# Speed profile of CSX 2121 and CSX 2738 (2026-11-08)

First measured speed profiles on the layout. Done on the Pi's JMRI with the block
detection sensors, one loco at a time on the full loop. No CV or roster entry was
changed. The follow-up is [`CV_CHANGES_DRAFT.md`](CV_CHANGES_DRAFT.md).

## Method

- The loop: East Main Ext, OS7b, Main East, OS33, East Lead, OS35a, OS37, K-2, K-1,
  OS39, OS35b, West Main Ext, OS23a, Main West, OS1, Brick-Plane, OS5, East Main Ext.
  The block lengths in `tables.xml` add up to **31,292.8 mm**. That length has not
  been checked against the Anyrail plan.
- Speed = loop length / lap time, one lap = two consecutive arrivals in East Main Ext
  (counted only after Switch 23a lit in between, so a sensor retrigger cannot count).
- Per step: one transition lap (discarded, the speed change disturbs it), then two timed
  laps (one at steps 8 to 16, where a lap takes 4 to 14 minutes).
- Throttle steps are on the 126-step scale. Lights (F0) on for detection; 2121's sound
  muted (F8). CS-105 over LCC, track power from the CS-105.
- 2738 ran **east** (its forward) and 2121 ran **west** (its forward). The K loop and
  the grades are driven in opposite directions, so a direction effect is mixed into
  the comparison. Not yet separated.
- Tools: [`runner/step_runner.py`](runner/step_runner.py) runs inside the Pi's JMRI
  (dropped through `jmri_cmd_watcher`), [`runner/move_to.py`](runner/move_to.py)
  moved a loco to a stopping condition, [`analyze_profile.py`](analyze_profile.py)
  turns the runner logs into [`results.csv`](results.csv). The raw `steprun_*.log` files
  are not in the repo (the tracked-file policy forbids `*.log`); `results.csv` and
  `manual_laps.csv` hold every lap used, and the runner writes the same log format again
  on a re-run.
  [`propose_table.py`](propose_table.py) calculates the draft table.

## Results (mean of the timed laps, loop = 31,292.8 mm)

| Step | CSX 2121 mm/s | CSX 2738 mm/s | 2738 / 2121 |
|---:|---:|---:|---:|
| 8 | 49.8 (2 laps, see below) | 37.0 | 74% |
| 12 | 93.3 | 54.7 | 59% |
| 16 | 139.3 | 72.4 | 52% |
| 24 | 225.7 | 108.1 | 48% |
| 32 | 304.8 | 143.6 | 47% |
| 48 | 380.2 | 215.5 | 57% |
| 64 | 420.4 | 287.1 | 68% |
| 80 | 403.5 | 360.4 | 89% |
| 96 | 424.5 | 425.6 | 100% |
| 112 | 414.8 | 434.0 | 105% |
| 126 | 429.6 | 433.8 | 101% |

Reading the scale as HO (1:87), 430 mm/s is about 84 scale mph.

## What the data says

1. **Same top speed, different curves.** Both locos top out at about 420 to 430 mm/s.
   2121 gets there by step 64, 2738 only by step 96. In between 2738 runs as little as
   47% of 2121's speed (step 32).
2. **2738 was linear.** Its CV25 is 0 ("Disabled, Speed Curves not used") and CV29 bit 4
   is clear, so the linear table in CV67 to CV94 was **not in use**. Its speed rises
   about 2.3 mm/s per step until the top. 2121 has CV25 = 16 (User Defined Speed Table)
   and CV29 = 50.
3. **Momentum differs.** 2121: CV3/CV4 = 26/24. 2738: 0/0.
4. **Repeatability at the top is about +-3%.** 2121's steps 80 and 112 came out 3 to 4%
   slower than steps 64, 96 and 126, a drift between runs, not a real dip.
5. **Step 8 of 2121:** the two valid laps are in [`manual_laps.csv`](manual_laps.csv)
   (633.0 s and 624.9 s, 1.3% apart). The suite's own step-8 laps were discarded.

## Data quality notes

- 2121 step 64 lap 2 of the first suite (ended at epoch 1794132972.8) was dropped: the
  loco rolled over a sheet of paper in Main East and was rerailed (the block dropped out
  for part of the crossing, the lap ran 5 s long). Step 64 has three other clean laps.
- 2121 step 8 and the first 2121 suite's second step-8 "lap" (71 s) were retrigger
  artefacts of the lap counter (East Main Ext flickers as a loco enters Switch 5). Fixed
  in the later runs; the artefact rows are not in `results.csv`.
- 2738 step 24 first attempt (`steprun_2738_a.log`, stalled after the dead spot beyond
  Switch 1) is not included; the second run repeated it.
- The two locos were measured in the same session, in opposite directions, after a
  track fault just beyond Switch 1 (it stopped both locos twice) had been fixed.

## Not done

- Step 126 repeat for drift; steps below 8 (creep); the opposite direction for each loco.
- Loop length check against the Anyrail plan.
- Scale at step 16 for 2738 took 45 s for 610 mm, far slower than anywhere else.
  Not investigated.
- Momentum has not been measured. The CV3/CV4 time scale of the two decoders is not
  confirmed from the JMRI definitions.
