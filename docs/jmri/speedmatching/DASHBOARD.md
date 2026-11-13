# Speed-match live dashboard

A browser page for the Mac that shows a speed-match run while it happens on the layout:
which loco, which throttle step, how fast it is going, which block it is in, and how the
speed curve is filling in. It only reads. Nothing is sent to JMRI, the layout or MQTT, and
nothing is written on the Pi.

Code: [`jmri/layouts/hart/scripts/speedmatch/dashboard/`](../../../jmri/layouts/hart/scripts/speedmatch/dashboard/)
(Python 3 standard library and plain HTML, CSS and JS; no build step). Steps for running a
profile are in [`RUNBOOK.md`](RUNBOOK.md).

## Start it

```
python3 jmri/layouts/hart/scripts/speedmatch/dashboard/server.py
```

Open <http://127.0.0.1:8765/>. Every 1.5 seconds the server runs `ls`, `stat` and `tail`
over ssh on the Pi (host from `HART_PI_SSH`, default `pi`, the same as `drop_job.sh`) and
reads the new bytes of the newest `steprun_*.log`, `stoptest_*.log`, `pass_*.log` and
`preflight_*.log` in `/tmp`. If the Pi cannot be reached the page says "Pi not reachable,
retrying" and carries on when it comes back.

| Option | Meaning |
|---|---|
| `--host 0.0.0.0` | listen on the LAN, so a phone can open it (default 127.0.0.1) |
| `--port 8765` | port |
| `--pi NAME` | ssh host, overrides `HART_PI_SSH` |
| `--interval 1.5` | seconds between polls |

## Preview without the layout

```
python3 jmri/layouts/hart/scripts/speedmatch/dashboard/server.py --demo
python3 jmri/layouts/hart/scripts/speedmatch/dashboard/server.py --replay /tmp/sm/steprun_*.log --rate 20
```

`--demo` makes up logs in the shape the distance-mode runner writes: CSX 2121 and CSX 2738,
both directions, on loop1 with the default steps 8, 16, 24, 32, 48, 64, 96 and 126, a 60 s
warm-up at step 48 before each loco's first run only, the momentum settle time, and at the end
two Switch 13 passes (steps 24 and 48) on loop2. Speeds are the 2026-11-08 result scaled by
1.122 (the loop was 12% longer than first thought), block lengths come from
`data/block_lengths.csv`, with a little noise. The step end rule is the runner's own, so the
slowest steps end as `max` and show as not valid. `--replay` plays real logs back with their own timestamps sped up by `--rate`
(default 20). Gaps longer than two minutes of log time are shortened so logs recorded days
apart play straight through. Add `?theme=dark` or `?theme=light` to the address to force a theme;
the Theme button does the same.

## What each panel means

- **Top bar.** Live, replay or demo mode, and whether the Pi answers. A red or amber banner
  appears for `STOP`, `ERROR`, `ABORTED` and `NO GUARD`; it stays until the run is replaced.
- **Hero.** The loco on the run (photo from `jmri/resources/roster`, model from the roster file),
  direction, route and status: warming up, settling, measuring, done, stopped or error with
  its reason. Throttle step out of 126 with a bar (ticks mark the steps of the run), live speed
  in mm/s and in HO scale mph (mm/s x 3.6 x 87 / 1609.34), elapsed time and a rough time left.
  The time left is the mean time of the steps done so far times the steps remaining, so it runs
  long early on, because the slow steps take the longest.
- **Step results.** A step that ends `settled` or `timed` is a measurement and goes on the
  curve. One that ends `max` (time ran out) or `stalled` is flagged and left off the curve, and
  a step with no reading (`n=0`) is a gap, never 0 mm/s. The flagged steps are listed above the
  chart. `EXTRA` (one more reading because the blocks spread too much) shows in the current-step
  panel.
- **Freeze.** After `FREEZE` the step takes no more blocks (late `BLOCK` and `SENS` lines are ignored) and the page says "step n done, computing" until `STEPDONE`.
- **Pass jobs.** A `pass_*` log shows a pass view in place of the step panel: the stretch
  from the `PATH` line (the sensors from the first to the last of the pass) (Switch 5 to Switch 15 for Switch 13) with the time
  each sensor lit after the pass started, the time across each block and the speed. The pass
  ends `passed`, or is flagged with its reason (`max`, `stalled`, `killed`, a guard). `wrong_way` gives a red banner, "pass went the wrong way, loco stopped".
- **Track.** The route's blocks in running order (reversed for a reverse run), width in
  proportion to length, with the name and length in inches. The block the loco last entered is
  outlined. Blocks crossed during the current step are tinted and show the measured mm/s.
  A hatched block has no known length.
- **Current step.** The block readings of the step being measured (length, time, mm/s), their
  sum, the average and the spread (standard deviation as a share of the mean), and the settle
  countdown before measuring starts. Logs from the older mode show their `READ` rows instead.
- **Speed curve.** mm/s against throttle step for the latest run of each loco and direction,
  points added as steps complete. One colour per loco, dashed for reverse. The faint dotted
  line is the 2026-11-08 result times 1.122. Hover for the values at a step; the Table button
  shows the same numbers as a table.
- **2738 against 2121.** Per step, 2738 as a percentage above or below 2121 for both forward
  and both reverse. Cells outside plus or minus 3% are shaded with an arrow.
- **Runs.** Every log seen, with loco, direction, steps done and status. Click one to look at it;
  "Follow live run" goes back to the one still running.
- **Events.** The last 15 lines of the focused run in plain words.

## Log lines it reads

Each line is `<epoch seconds> <message>`. It reads `RUN`, `CFG`, `LENGTHS`, `WARMUP`,
`WARMUP_DONE`, `WARMUP_LAP`, `STEP`, `SETTLE`, `MEASURE`, `SENS`, `BLOCK`, `EXTRA`, `FREEZE`, `READ`, `STEPDONE`, `PATH`,
`PASS`, `PASSDONE`, `STOP`, `END`, `ERROR`, `ABORTED` and `NO GUARD`. Lines it does not know are
skipped. Logs from before distance mode (`READ`, `median=`, `WARMUP ... laps=`) still show.

Tests: `jmri/layouts/hart/scripts/tests/test_speedmatch_dashboard.py`, run by `./tools/check.sh`.
