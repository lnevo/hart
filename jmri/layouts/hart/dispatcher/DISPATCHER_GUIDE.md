# HART Railroad — Auto Dispatcher Guide

**Publication:** DS-AUTO · Rev A · Eff 2026-08-20
**Railroad:** HART Railroad · Pittsburgh & Chartiers Valley Division · Neville Island Operations
**Scope:** JMRI Dispatcher System on PanelPro (panels **Dispatcher System** and **HART Railroad**)

This is how you **send a train** from one station to another, or along a
named list of stations. You click stations; the system picks the path, throws
turnouts, and runs the locomotive.

It is **not** the CTC machine. Authority and signal Hold still belong to CATS
or the USS panel. Run **either** CATS CTC **or** the USS machine — never both —
and do not start Dispatcher System from inside CATS. Use PanelPro.

CTC desks: [`../ctc/DISPATCHER_GUIDE.md`](../ctc/DISPATCHER_GUIDE.md) (USS) ·
[`../../../cats/docs/DISPATCHER_GUIDE_CTC.md`](../../../cats/docs/DISPATCHER_GUIDE_CTC.md)
(Digicon).

---

## 1. What you click

Two windows:

| Window | What it is |
|--------|------------|
| **Dispatcher System** | Command panel: start/stop, register trains, Run Dispatch vs Setup Route vs Run Route |
| **HART Railroad** | The stations. The **loco + short name** is the destination. The **circuit to its left** is progress. The **circuit below-left of the loco** is occupancy, except Engine House **EH-1…EH-3** where occupancy sits further left on the same row |

Stations, west → east around the plant, then the yard and house:

| Station | Where it is |
|---------|-------------|
| **Brick-Plane** | Hairpin between Brick and Plane |
| **East Main Ext** | Main between Plane (102) and Barn (117) |
| **Main East** | Main south of the yard, approaching East End |
| **East Lead** | East End lead off 112; destination label **E Lead** |
| **Main West** | Main West at East End (around-the-room from Brick) |
| **West Main Ext** | Main West between East End and Princess |
| **McKees Rocks** | Princess, north branch |
| **McKeesport** | Princess, south branch |
| **Scale** | Left of the engine house, Plane–117 lead; destination label **Scale** |
| **Barn** | Immediately to the right of Scale (Barn lead); destination label **Barn** |
| **EH-1 / EH-2 / EH-3** | Right of the 116 ladder |
| **S-1…S-5** | South Yard body; destination labels **S-1…S-5**, aligned with Main W / Main E |
| **W-1 / W-2** | Brick yard body |
| **K-1 / K-2** | Princess stubs east of 115 / 114; destination labels **K-1** / **K-2** |

You can only start and stop at those stations. Occupancy icons and MoveTo
buttons are in place. **Stage 1 was re-run 2026-08-22** after hidden yard
throats (graph is **91 sections / 688 transits / 1508 traininfo**). Every listed
station is a valid **start and destination**, including **S-1…S-5**
(enter/leave via 103 or East Lead). Manual Princess pairs (`113RA→115LA`,
`113RB→114LA`) were re-added after Discover. After any future Stage 1:
`python3 jmri/layouts/hart/scripts/fix_traininfo_detection.py` then
`reconcile_dispatcher_stations.py`. Never run Stage 1 or store tables from
CATS.

---

## 2. Session start (once)

1. Open **PanelPro** (not CATS). Load the HART tables.
2. Put the train on the rails at a station. Release it from WiThrottle — do not
   keep a phone throttle on that address.
3. On **Dispatcher System**, click **Run Dispatcher System** → OK.
4. Leave **Simulate Dispatched Trains** **off** for a real train (on only to
   dry-run with no locomotive).
5. Turn **Dispatch Path must be clear** **off** unless the whole train sits
   inside one station block. If the tail occupies the next block, a “path must
   be clear” wait will never finish.
6. **Express Train (no stopping)** **on** = go to the destination with as few
   stops as possible. **Off** = stop at every station on the way.

---

## 3. Register the train (once per session, or after you move it by hand)

1. Click **Setup Train in Section**.
2. Choose **1 train** (or several if you are registering more than one).
3. Pick the station block the engine is in, then the roster entry. Every
   DecoderPro loco with a speed profile is listed (the full HART roster).
   Dispatcher System hides locos that have no profile; `ensure_dispatcher_roster_profiles.py`
   writes the same synthetic 10-step / 400 mm/s profile 2091 already had.
4. A neighbor block highlights. Answer **which way the train is facing** —
   toward that highlight, or the other way. That is polarity, not the route.
   Stock Dispatcher System used to invert that answer (see
   [`DISPATCHER_LAYOUT_HOOPS.md`](../../../wiki/DISPATCHER_LAYOUT_HOOPS.md));
   HART’s overlay stores what you clicked and uses it on the **first** dispatch.
   If the loco still backs, release WiThrottle and re-register — do not “fix
   facing” by editing mast slots.
5. Accept length and speed factor if they look right.

The station label on **HART Railroad** should show the train name. If you lift the
train to another station by hand, register it again there.

---

## 4. Send it to one station (no saved route)

Use this when you just want “go to Main East.”

1. Click **Run Dispatch** so it is selected (**Setup Route** must be off).
2. On **HART Railroad**, click the **wide label** of the destination station.
3. Pick the train if asked, and Express vs stopping if asked.

The system takes the **shortest** path (block lengths). It does **not** ask
which plant to go through. From East Main Ext to Main East that is normally
east through 117b, not around through Plane.

**To force a path that is not the shortest**, do not use this mode. Build a
route that lists the stations you want it to visit (section 5).

---

## 5. Pick a few stations, then reuse that as a named route

Use this when you want a specific itinerary: stop here, then here, then there.

### Build it once

1. Click **Setup Route** (**Run Dispatch** turns off).
2. On **HART Railroad**, click stations **in the order the train should visit
   them**, starting where it is (or where it should begin).
3. After each click, choose **Select another station** until the last stop,
   then **Complete Route**.
4. Click **Finish selecting routes** when you are done creating.

Skip **Set Action…** unless you know you need a station script.

Name is assigned from the first and last stations. Review it under
**View/Edit Routes**. To drop a stop, edit the route and use the delete-row
checkbox. To add a stop, build a new route — there is no insert.

### Run it later

1. Train registered, sitting at (or able to reach) the first station.
2. Click **Run Route**.
3. Choose **1 route**.
4. Pick the train. Prefer **show routes starting at train position**.
5. Pick the route, then:
   - **Run the route and stop**
   - **Run the route and return to the start** (shortest way back, not
     necessarily the same stations)
   - **Run, return, and repeat**

That is the “predefined route” workflow. Build once, run whenever the train
is in place.

### Example

Train on **East Main Ext**, facing east, want Barn then East End without
going the long way around Plane:

**East Main Ext** → **Main East** → **East Lead**

To send it the long way on purpose, put **Brick-Plane** (and
whatever else you need) in the list so shortest-path cannot skip it.

---

## 6. When it will not start

| What you see | What to do |
|--------------|------------|
| Console: `waiting for route … to be clear` | The wait started with **Dispatch Path must be clear** on, and some block on that transit is occupied — often **this train’s tail** in the next station. Cancel, turn that button **off**, then click the destination again. Turning it off after the wait has started does nothing. |
| Train sits, no motion | Confirm **Run Dispatch** (one-shot) or that **Run Route** actually started a route. Confirm the train is registered in the station it occupies. |
| Goes the “wrong” way around the plant | One-shot dispatch always takes the shortest path. Build a **Setup Route** that includes the stations on the path you want. |
| Runs backward | Facing was wrong, or a WiThrottle still owns the loco. Release the phone, terminate, re-register facing, dispatch again. Do not nudge an auto train with the throttle. |
| Stuck after a derail / pickup | **Modify Dispatcher System**: refresh, delete the transit if it is still listed, re-register the train where it now sits. **Change Dir** there if it is pointed the wrong way. |

To abort: **Stop Dispatcher System**, or Modify Dispatcher System → delete the
active transit. Then **Run Dispatcher System** again before the next move.

---

## 7. Buttons you can ignore (for this desk)

Leave these alone until someone is tuning the railroad: **Set Stopping Length**,
**Set Stop Sensor**, **Set Station Wait Time**, **Set Station Direction**,
**Restrict Transit Operation**, scheduler / timetable / analog clock.

**Set Station Direction** is the advanced way to forbid one exit from a
station (so shortest-path cannot use it). Prefer a named route with extra
stations unless you are locking a one-way plant for the session.

---

## 8. Quick recap

| Goal | Clicks |
|------|--------|
| Register a train | **Setup Train in Section** → block → roster loco → facing |
| One destination | **Run Dispatch** → click destination label |
| Same trip every time | **Setup Route** → click stations in order → **Complete Route**; later **Run Route** → pick that route |
| Stop at every station | **Express Train** **off** |
| Skip intermediates | **Express Train** **on** |
| Tail hanging out of the station | **Dispatch Path must be clear** **off** before you click |

---

## 9. NX on HART Railroad (separate desk)

JMRI Entry/Exit lives on **HART Railroad** as a **white USS lamp** on the
approach track into each CTC switch (`NX 100L`, `NX 102LB`, …). It turns
**green** when that end of a route is active. That is not the Dispatcher
System pair: the **loco** is MoveTo, the **small track-circuit square** is
progress.

**Now (SML mode):** click two white lamps to throw the path and let SML
set the facing mast. Default AAR icons stay. LE turnout circles still
work. NX does not Hold or reserve blocks.

**Later (lock mode):** `python3 jmri/layouts/hart/scripts/apply_nx_layer.py --mode lock`
then deploy. After that, NX Holds every source mast at Stop until you
click a route, and reserves the path. Use that desk **instead of** CATS
CTC and USS Logic. Switch back with `--mode sml`.

You can also flip it in PanelPro: **Tools → Entry Exit** — pair type
**Turnout and Signal Mast Logic** vs **Full Interlock**, and **Use ABS
Signal Mode**. Store from PanelPro if you change it there.

1. Open **PanelPro**.
2. Click the white lamp, then the exit lamp to line turnouts / SML.
3. First prove-out pair: **NX 100L → NX 102LB** (Brick main) and
   **NX 101RA → NX 100L** (W-1 out).

Do not click Dispatcher System **MoveTo** labels as NX points — those are a
different desk. Hand-throws 116/118/119 and yard stubs are not NX ends.
