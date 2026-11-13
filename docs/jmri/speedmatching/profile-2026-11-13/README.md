# Speed profile and match of CSX 2121 and CSX 2738 (2026-11-13)

The re-run planned in [`RERUN_PLAN.md`](../RERUN_PLAN.md), done with the tools in
[`RUNBOOK.md`](../RUNBOOK.md) on the Pi's JMRI, CS-105 over LCC. Both locos were profiled in
both directions, 2738 was adjusted on the main to match 2121, the momentum of the two was
compared, and both roster entries now carry the measured speed profile. 2121 was not changed.

## Result

2738 now matches 2121 within 4% at every step from 24 up, in both consist pairings (most steps
within 2 to 3%). Step 16 is +2.1% in one pairing and +6.1% in the other against 2121's latest
reading, +2.9% against the mean of 2121's two readings there. The tolerance is 5%: run-to-run
repeat at one step is about ±2%, and up to 6% at slow steps, so a tighter target would chase
noise.

| Step | 2121 fwd | 2121 rev | 2738 fwd | 2738 rev | 2738 rev vs 2121 fwd | 2738 fwd vs 2121 rev |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 50.6 | 50.9 | 60.3 | 61.4 | +21% | +18% |
| 16 | 156.3 | 161.9 | 171.8 | 159.6 | +2.1% | +6.1% |
| 24 | 261.7 | 272.8 | 270.0 | 253.2 | −3.2% | −1.0% |
| 32 | 338.8 | 358.7 | 354.1 | 341.9 | +0.9% | −1.3% |
| 48 | 429.0 | 440.5 | 447.6 | 419.4 | −2.2% | +1.6% |
| 64 | 454.1 | 493.7 | 484.5 | 472.0 | +3.9% | −1.9% |
| 96 | 453.4 | 484.6 | 479.3 | 466.1 | +2.8% | −1.1% |
| 126 | 465.0 | 499.9 | 490.3 | 466.3 | +0.3% | −1.9% |

mm/s, from [`profile.csv`](profile.csv) as written to the roster. In the consist the locos face
away from each other, so 2121 forward runs with 2738 reverse and the other way round.

- Step 16 for 2121 reverse read 171.9 in its full run and 161.9 in the re-run; against their
  mean (166.9) 2738 forward is +2.9%. It is the noisiest reading of the day.
- Step 8 is creep: 2738 is about 20% faster there and cannot be brought down without its start
  voltage or the bottom of its table. Left as it is.

## What changed on 2738

Written on the main through the guard ([`POM_GUARD.md`](../POM_GUARD.md)), old values from the
roster (`ROSTER_OLD_OK`), consist broken first. Rollback files and the ledger are kept off the
repo with the raw logs (see below).

| CV | Old | New | Why |
|---|---:|---:|---|
| 66 (forward trim) | 128 | 135 | 2121 runs 3 to 10% faster in reverse than forward; 2738 is even both ways. Raising only 2738's forward (×1.055) matched 2121 reverse without touching the other pairing |
| 69 (table entry 3) | 50 | 51 | step 16, split between the two pairings |
| 70 (table entry 4) | 73 | 74 | step 16, split between the two pairings |

The roster entries of 2738 still hold the old values until the programming-track read-back.

## Momentum

Solo stop tests, same track, same trigger, 2738 forward and 2121 reverse (east):
[`stoptests.md`](stoptests.md). At step 32 and step 96 every sensor after the stop command lit
within 0.2 s for the two locos, and both came to rest in the same block. 2121 slows more
gently than the linear CV4 estimate (about 3.9 m covered in the first 8.4 s from step 96), and
2738 matches it. The test of the coupled pair did not run cleanly (Switch 33 was closed under it);
the solo match stands for it.

## Roster speed profiles

Written into both roster entries on the Pi (8 points each, key = step / 126 x 1000), then synced
to the Mac and Windows: [`payload_2121.json`](payload_2121.json),
[`payload_2738.json`](payload_2738.json). Each direction is merged from its runs
(`profile_to_roster.py --merge`, per step the latest complete run that settled it; `sources` in
each payload names the runs). 2738's forward points are from after the CV66 change. 2121's
forward step 8 was set by hand to 50.6, the clean Main West block; the run's own value (54.7)
includes one flicker reading.

## Switch 13 and Switch 7 on loop 2

Two timed passes from Switch 5 to Switch 15 and a lap survey: [`loop2_placement.md`](loop2_placement.md).
OS Switch 7 (Scale side) centre 4249 mm and OS Switch 13 centre 5457 mm from Switch 5's points
(passes agree within 27 mm; the survey within 20 mm). The passes also give Scale about 3645 mm
and Barn about 770 mm (the table has 610 mm for both). The survey got one usable lap only, so its
short-block lengths are not reliable. Nothing is applied to `block_lengths.csv` yet.

## Faults found and fixed during the run

- `cs105_consist.py` detach sent no flags byte, so the CS-105 ignored it.
- A direction set as soon as the throttle arrived was overwritten by the train node's report,
  so a loco ran the way it last ran. Jobs now wait, set, check and retry (`DIR ... held`).
- Jobs switched F0 off at the end; a standing 2738 (no sound) then reads free.
- A block lighting again behind the loco can be taken as the next block (seen on 2121 at step 8).
  Not fixed yet.

Runs made before the direction fix carry the asked direction, not the real one. The 11:43 2738
"forward" run went west and is left out; the others were checked against the travel the
analysis reads.

## Data

`profile.csv` is the analysis of the runs used. The raw logs (34 files: step, pass, stop-test
and move logs), the guard ledger and both rollback files are on the Mac in
`~/speedmatch-logs/2026-11-13/`; the repo does not hold `*.log` files.
