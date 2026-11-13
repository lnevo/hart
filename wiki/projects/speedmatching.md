# Speed matching

- **Owner:** lnevo
- **Status:** Re-run ready to start on the layout (2026-11-13). Everything that can be done off the layout is merged; the handoff is below. 2738 was matched to 2121 on 2026-11-08 (PR #187).
- **Saved:** 2026-08-21 from [jmriusers #254859](https://groups.io/g/jmriusers/message/254859)

HART auto-dispatcher needs **measured** roster speed profiles for station stops. Apart from 2121 and 2738, every live DecoderPro loco still has the same synthetic 10-step / 400 mm/s profile. This thread is a working club procedure for a detected track circle plus JMRI POM scripts.

## Handoff: the re-run (2026-11-13)

Done and merged: loop block lengths from the AnyRail 5.3b staging level, pinned to the plan
turnouts (#399, deployed to the Pi and Windows; loop is 35.1 m, so the 2026-11-08 speeds were
about 12% low; the barn crossover is 163 in from Switch 5's points, confirmed by the owner);
measuring tools (#397); write guard for programming on the main (#398); roster speed-profile
writer, stop test, default guards (#407); loop 2 through S-R, Scale and Barn (#410).
Runbook: [`RUNBOOK.md`](../../docs/jmri/speedmatching/RUNBOOK.md). Guard:
[`POM_GUARD.md`](../../docs/jmri/speedmatching/POM_GUARD.md). Lengths method:
[`ANYRAIL_LENGTHS.md`](../../docs/jmri/speedmatching/ANYRAIL_LENGTHS.md).

Owner decisions: profile both locos in both directions first, then the owner picks the
correction pairing and the tolerance (the locos run facing away from each other, both
directions). The decoder read on the programming track is skipped for 2121 and 2738: the
roster holds every CV from a full DecoderPro read (Pi and Mac copies identical, 2026-11-13),
so the first write needs `ROSTER_OLD_OK = True`. 2738 is a TCS motor-only decoder (no sound);
`--mute-sound` is for 2121 only. The McKees stub detectors are not on a node yet, so they
cannot be guarded.

None of the Jython in `speedmatch/jython/` has run in JMRI yet; the first pass is its first run.
Distance mode and the pass job (2026-11-13) were added so the whole layout procedure takes about
40 minutes; the runners also run in a simulation in the tests.

Steps left, in order (PanelPro running on the Pi, owner not operating, only the test loco moves).
Steps 1 to 4 are the 40-minute procedure in the [`RUNBOOK`](../../docs/jmri/speedmatching/RUNBOOK.md):

1. **Break the 2121/2738 LCC consist** (`cs105_consist.py` detach), line up loop 1 and build the
   jobs (5 min). While the consist stands, commands to 2121 also move 2738.
2. **Profiles on loop 1, distance mode** (`make_job.py steps --mode distance --guard default`;
   steps 8, 16, 24, 32, 48, 64, 96, 126): 2121 forward with a 60 s warm-up (about 6 min; its first
   two steps are the shakedown, watch the log live), 2121 reverse (5), 2738 forward with a 60 s
   warm-up after the swap (9), 2738 reverse (6).
3. **Switch 13 on loop 2** (8 min): line up loop 2, then two passes from Switch 5 to Switch 15 at
   steps 24 and 48 (`make_job.py pass`), then
   `infer_block_lengths.py --route loop2 --locate --pass-log <logs>`: places Switch 13 and the
   Scale-side half of Switch 7 between Switches 5 and 15, reports both passes and their
   difference.
4. **Fetch and analyse** (1 min, `analyze.py`); the owner picks the pairing and tolerance. The lap
   survey on loop 2 (`--route loop2`, steps 32, 48, 64) stays available for the lengths of Scale,
   Barn, S-R, OS 23b and OS 31.
5. **Correct 2738's table**: `correct.py` proposal, guard dry run, then apply with
   `ROSTER_OLD_OK`, `CONSISTS_BROKEN` and an `ABSENT_OK` list built from a consist query.
   Re-measure and repeat until within tolerance.
6. **Remake the consist** and run the stop test at steps 32 and 96.
7. **Write the measured profiles** into both roster entries on the Pi (`make_job.py profile`),
   then sync the roster to the Mac and Windows.
8. **Read back** both decoders on the programming track, update the roster, archive the guard
   ledger (`pom_guard.py archive-ledger`).
9. **Record** the results in a dated folder next to `profile-2026-11-08/`, and update this
    page and `wiki/STATUS.md`.

## First measurements (2026-11-08)

Method: a runner inside the Pi's JMRI (the `jmri_cmd_watcher` channel) steps one loco through
the throttle steps around the full loop and times laps from the East Main Ext block sensor
(loop 31,292.8 mm from the block table; not yet checked against Anyrail). 2121 and 2738 reach
the same top speed (about 420 to 430 mm/s) but 2738 is 47 to 70% of 2121's speed from step 12
to 64, because 2738's speed table was switched off (CV25 = 0, CV29 bit 4 clear) and it has no
momentum (CV3/CV4 = 0/0). The owner chose to match 2738 to 2121, momentum included. Draft:
[`CV_CHANGES_DRAFT.md`](../../docs/jmri/speedmatching/profile-2026-11-08/CV_CHANGES_DRAFT.md).
The owner wanted no programming on the main while other engines were on the track; since
2026-11-12 it is allowed behind guardrails that rule out broadcast commands (re-run plan, Part C).

**Next (2026-11-12):** [`RERUN_PLAN.md`](../../docs/jmri/speedmatching/RERUN_PLAN.md):
block lengths from the AnyRail plan as a source of record, better tools, programming on the
main behind guardrails, and a re-run of 2121 and 2738. No fleet target curve until more locos
are profiled.

**Handoff for the test agent (2026-11-12, evening):** Parts A to C of the re-run plan are not
built yet, so Part D cannot start; the tools are still the 2026-11-08 ones. 2121 and 2738 are
still in the CS-105 consist, so driving either moves both (an unexpected move of the pair caused
a short at Switch 9 earlier the same day); break it with `cs105_consist.py` only after asking the
owner. 2121 stands in East Main Ext; 2738 was on Scale (not Barn, as JMRI had it) before the pair
moved together, so confirm where it is now with the owner. K-1 and K-2 are clear. Other locos,
as last reported: 1827 on W-2, 572 on W-1, 9602 on EH-1, 4678 on EH-2, 1993 on McKeesport.
PanelPro on the Pi was quit normally at 21:25 with no Store, so the block values must be set again
when it is restarted. Switch 9 was rewired (normal EH-2, thrown EH-3) and the Layout Editor and CATS
follow it (PRs #369, #370). Over the CS-105 LCC throttle, F0 reads back False after it is set,
so check lights by eye. Detection is current-based, so a standing loco can read free.

Open: consist testing; step 126 drift check; opposite-direction check; Anyrail
loop length; a clean timing pass through Scale (the earlier 45 s was a hand block); the reverse profile of 2738 (2121's reverse matches its forward); the STRR scripts below are still unused.

## Source

**Thread:** Re: Anyone using a track circle for speed matching?  
**Author:** Eric W. Bradford (STRR / Short Track Rail Road, Vista CA)  
**Date:** 2026-08-21, 3:26am (#254859)  
**Lineage:** Phil Klein original script → Bradford 2013 mods → Bradford 2025 refresh for JMRI 5.12 / Java 17

## Files (in-repo)

| File | Role |
|------|------|
| [`STRR Speed Match-Measure Table SOP Rev2.pdf`](../../docs/ops/STRR%20Speed%20Match-Measure%20Table%20SOP%20Rev2.pdf) | Club SOP (37 pages) |
| [`STRR_Speed_Match_Script_N-Scale_v4.2(NC+STRR_99_XtraSteps).py`](../../docs/jmri/speedmatching/STRR_Speed_Match_Script_N-Scale_v4.2(NC+STRR_99_XtraSteps).py) | Automated speed **matching** (load this first) |
| [`STRR_Speed_Measure_Script_v1.1.py`](../../docs/jmri/speedmatching/STRR_Speed_Measure_Script_v1.1.py) | Live speed **measuring** + stddev (sound / POM workaround) |

Load Matching, then Measuring. Reverse order throws errors (Bradford has not fixed that yet).

## What the post says

- Table is a detected loop similar to Steve Todd’s original post: **12 unique Kato N 19″ Unitrack sections**, one BDL168 sensor per two pieces (sensors `LS1`–`LS12` in the scripts).
- Hardware that works: Digitrax **DCS100** + DecoderPro (also Zephyr DCS50 / DCS52). Detection: **BDL168**.
- About **15–20 minutes per loco**; low-speed search is the slow part. Kato low-speed is excellent.
- Non-sound decoders behave better. Sound often needs low/high ends set first; the Measure script shows live scale speed and standard deviation so you can POM by hand with the same step logic.
- Target top speed **99 n-scale mph** so Digitrax throttle 0–99 means mph, and locos can hurry back to the yard.
- Script warms up **2.5 laps**, direction is selectable (consist orientation). Programs speeds **11 through 99 in multiples of 11**.
- Club mixes road power, mid-train, and a switcher on 30–40 cars after matching.

Scripts are **N-scale / Kato 19″ geometry**. HART is not that loop — adapt sensor names, piece count, radius, and scale before running anything here.

## Message (cleaned)

Eric Bradford: one of the people who modified Phil Klein’s speed matching script in 2013; also mentioned in the PDF from earlier in the thread. Stepped away ~10 years; back with an N-scale club in Southern California.

They built a club table like Steve Todd’s. Last year he refreshed the script for JMRI 5.12 / Java 17 on an N-only loop of 12 Kato sections. Regular use: ~15–20 min per loco. Non-sound works better than sound. Members mix loco types. Program to 99 n-scale mph so Digitrax 0–99 has meaning. Example consist: 3 SD60s on the point, 2 SD-24s mid-train, switcher on the rear of 30–40 cars.

Updated script sets speeds 11–99 in multiples of 11, 2.5-lap warmup, selectable direction. Block count tuned to keep programming time down. Comments in the script explain each line (view in VS Code).

Now DCS100 + DecoderPro; table also ran on Zephyr DCS50/DCS52. BDL168 for detection.

Sound workaround: Measure script shows live speed values and standard deviations around the circle for POM. Same speed-setting logic as the automated script lets sound and non-sound consist together.

Attachments: SOP, Speed MATCHING script, Speed MEASURING script. Load Matching first, then Measuring.

Offer: SoCal visitors welcome on weekends. “If you are not having fun, you are doing something wrong!”

## Next (when we do this)

- [ ] Decide: adapt this circle-table method vs stock JMRI Roster ▸ Speed Profiling on a known-length HART block
- [ ] Replace each loco’s synthesized profile with a measured one
- [ ] If adapting the STRR scripts: HO scale, our detection sensors, straight/block length or loop geometry — do not run the N-scale constants as-is
