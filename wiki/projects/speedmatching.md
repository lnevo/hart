# Speed matching

- **Owner:** lnevo
- **Status:** Parked — CSX 2121 and CSX 2738 measured on the full loop 2026-11-08 ([results](../../docs/jmri/speedmatching/profile-2026-11-08/README.md)); 2738 was programmed to match 2121 (speed table, CV25/CV29, momentum) and a four-step re-measure shows it within 1.2% of 2121 from step 24 up (5.3% fast at step 12); its roster entry was updated by hand on the Pi and Mac, then synced to Windows from the Pi on 2026-11-08. Every other roster loco still has the same synthesized 10-step / 400 mm/s profile.
- **Saved:** 2026-08-21 from [jmriusers #254859](https://groups.io/g/jmriusers/message/254859)

HART auto-dispatcher needs **measured** roster speed profiles for station stops. Apart from 2121 and 2738, every live DecoderPro loco still has the same synthetic 10-step / 400 mm/s profile. This thread is a working club procedure for a detected track circle plus JMRI POM scripts.

## First measurements (2026-11-08)

Method: a runner inside the Pi's JMRI (the `jmri_cmd_watcher` channel) steps one loco through
the throttle steps around the full loop and times laps from the East Main Ext block sensor
(loop 31,292.8 mm from the block table; not yet checked against Anyrail). 2121 and 2738 reach
the same top speed (about 420 to 430 mm/s) but 2738 is 47 to 70% of 2121's speed from step 12
to 64, because 2738's speed table was switched off (CV25 = 0, CV29 bit 4 clear) and it has no
momentum (CV3/CV4 = 0/0). The owner chose to match 2738 to 2121, momentum included. Draft:
[`CV_CHANGES_DRAFT.md`](../../docs/jmri/speedmatching/profile-2026-11-08/CV_CHANGES_DRAFT.md).
The owner wants no programming on the main while other engines are on the track.

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
