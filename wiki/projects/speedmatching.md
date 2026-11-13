# Speed matching

- **Owner:** lnevo
- **Status:** Re-run done on the layout 2026-11-13: both locos profiled both ways, 2738 matched to 2121 within 4% from step 24 up (CV66, CV69, CV70 on 2738), momentum matched, roster profiles written. Left: programming-track read-back, loop 2 lengths into the tables. Record: [`profile-2026-11-13/`](../../docs/jmri/speedmatching/profile-2026-11-13/README.md).
- **Saved:** 2026-08-21 from [jmriusers #254859](https://groups.io/g/jmriusers/message/254859)

HART auto-dispatcher needs **measured** roster speed profiles for station stops. Apart from 2121 and 2738, every live DecoderPro loco still has the same synthetic 10-step / 400 mm/s profile. This thread is a working club procedure for a detected track circle plus JMRI POM scripts.

## Handoff after the re-run (2026-11-13, evening)

Done on the layout, results in [`profile-2026-11-13/`](../../docs/jmri/speedmatching/profile-2026-11-13/README.md):
both locos in both directions, Switch 13 and Switch 7 placed on loop 2, 2738 adjusted on the main
(CV66 128 to 135, CV69 50 to 51, CV70 73 to 74; 2121 unchanged), solo stop tests matched within
0.2 s, consist remade (flags 0x0A both ways: follower reversed, functions linked except F0),
measured profiles written into both roster entries on the Pi and synced to the Mac and Windows.
The pair is parked on EH-3 (Switches 13, 11 and 9 thrown), track power off.

Owner decisions: tolerance 5% (run-to-run repeat is about ±2%, more at slow steps); change only
2738, never 2121; the consist does not link F0, so the trailing headlight stays off.

Left, in order:

1. **Read back** both decoders on the programming track, update the roster (Pi first, then
   `tools/hosts/sync_roster_from_pi.sh --all`), then `pom_guard.py archive-ledger "CSX 2738"` on
   the Pi. Until then the roster holds 2738's old CV66, CV69 and CV70.
2. **Loop 2 lengths:** apply the Switch 13 and Switch 7 placement and the Scale (about 3645 mm),
   Barn (about 770 mm) and S-R lengths to `block_lengths.csv`, PanelPro closed. A proper survey needs
   a higher `--max` so each step gets 3 or more laps; the 2026-11-13 survey got one.
3. **Pair stop test:** the coupled run was spoiled (Switch 33 closed under it); repeat it from East
   Lead at steps 32 and 96 when convenient.
4. **Runner:** a block lighting again behind the loco is taken as the next block (2121, step 8).

Lessons from the run (also in the RUNBOOK's known limits): on the CS-105 a direction set at once
is lost (fixed: `DIR ... held`); a standing 2738 reads free with its lights off (jobs now leave F0
on); with CV4 = 24 a loco stopped from top speed rolls about 8 to 9 m; the pair test needs Switch
33 checked before it starts.

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
