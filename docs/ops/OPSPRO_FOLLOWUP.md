# HART Operations Pro: what is outstanding after the build

Written 2026-11-02 after the owner's review of the build on branch `agent/claude/opspro-build` (PR #120). Three lists: what the railroad still needs, what happened to the plugin list, and why the audit findings that remain are not a to-do.

## 1. The railroad

| # | Item | Who | When |
|---|---|---|---|
| R1 | **Done 2026-11-02:** merged and deployed. The Pi's previous files are saved in [`archive/operations-pi-2026-11-02/`](../../archive/operations-pi-2026-11-02/) | owner | next |
| R2 | Run the `Session` automation on the Pi with the plugin's live lane (`ops_install_agent`, then `ops_live_automation`), through one real session. The ordered test on copies proved the order; a live JMRI has not run it | owner with an agent | first session after deploy |
| R3 | Replace the 60 ft per spot (70 at A. Stucki) with measured spur lengths, and the halved South Yard lengths with the real split, when the main level is built | owner | main level |
| R4 | Place the 29 unplaced cars if they should enter service: 10 no-photo freight cars and HART 1776 can go to South Yard as empties; the passenger cars and cabooses need a track that takes their types | owner | any time, `place_car` |
| R5 | Watch the two Steel Plate flatcars that started loaded with no final destination: they went offline once and come back as Steel for A. Stucki. Expected, but check after session 1 | agent | after session 1 |
| R6 | Tune move counts after two or three real sessions: the STG trains' 30 moves, NVL's industry moves (8/3/4/5/5/3) and the random 50 on the IX lines were set by reasoning, not by running | agent | after session 3 |
| R7 | Keep the car repository and the roster in step as mapping section 10 proposes: `bin/cars publish` derives the Operations type from the STS code and the coke-fleet list, adds cars with no location, and `bin/cars compare` reports type, length and weight differences | agent | separate job |

## 2. The plugin

**Done 2026-11-02:** all 19 items closed in plugin 0.2.0 (PR 13, merge 99173a9), 850 tests passing, installed here at local scope. Per-fault results are in [`opspro-build/plugin_faults.csv`](opspro-build/plugin_faults.csv).

Three came out differently from this list's proposal:

- **Held spur (F7):** the refusal stays. JMRI writes `holdCustomLoads` only for a track with a schedule (Track:2935-2943), so allowing it would lose the setting on the next save. `add_industry` sets it, and the refusal now says so.
- **Engine road on a train (F10):** the refusal stays, as Edit Train offers only roster roads. The skill now puts locomotives before trains.
- **Lesson L18 was corrected:** alternates are never direct destinations (`Location.getTracksByMoves` removes them). A default car bound for a full spur overflows onto one. The skill carries that version, with the same fix: a load filter excluding E and L.

Two were not what the fault said. A same-named schedule (F13) was already refused, not shared silently; `schedule` and `share_schedule` now give a way through. `update_car type` (F17) already worked but was unlisted; it is now listed and checked.

`ops_dry_run` with `order` replaced `opspro-build/ordered_session.py`, which is retired. On a copy of this folder the same eleven builds took seconds in one JMRI, against about six minutes chained, and nine of eleven car counts matched [`opspro-build/ordered_session.csv`](opspro-build/ordered_session.csv); the other two differed by one car, within the builder's randomness. To repeat it:

`["D749", ["NVL", "CK1"], "STG-DEMMLER", "D749 Return", "STG-SCULLY", "D749", ["NVL", "CK1"], "STG-DEMMLER", "D749 Return"]`

`order` runs each group to terminate before the next, so it does not reproduce the overlap in `Session`, where NVL and CK1 build while D749 is out and terminate after D749 Return builds. The closer test is `Session Replay` set as the startup automation on a copy, which the dry run now traces. Two sessions on 2026-11-02 ran all 13 steps with no JMRI errors: D749 13 and 21 cars, NVL 20 and 17, CK1 3 and 1, STG-DEMMLER 18 and 25, D749 Return 8 and 13, STG-SCULLY 21 and 11. Watch CK1's single car in session 2 under R6.

## 3. The audit findings that remain

Nothing here is a defect. They stay because of decisions the owner confirmed.

| Rule | Count | Why it stays | Goes away when |
|---|---|---|---|
| type-no-track | 5 | Baggage, Coach, Combine, Dining and Observation exist for the unplaced passenger cars (D24) | R4 places them on a track that takes the types |
| car-unplaced | 29 | Cars STS does not position start with no location (D24) | R4 |
| route-stop-dead | 1 | CK1's Scale stop weighs the coke pull and does no work (D1) | never; it is the design |
| train-not-on-list | 4 | D749 only sets out and D749 Return only pulls at Demmler; only CK1 pulls K-1 and K-2 (D9) | never; they are the restrictions |

If the passenger cars stay unplaced for good, the five `type-no-track` errors can be silenced by giving S-R those five types, which costs nothing while the cars have no location.
