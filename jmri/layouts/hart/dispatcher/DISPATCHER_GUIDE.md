# HART Railroad — Auto Dispatcher Guide

**Publication:** DS-AUTO · Rev A · Eff 2026-08-20
**Railroad:** HART Railroad · Pittsburgh & Chartiers Valley Division · Neville Island Operations
**Scope:** JMRI Dispatcher System on PanelPro (panels **Dispatcher System** and **My Layout**)

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
| **My Layout** | The eight stations. The **wide label** is the destination button. The **small bubble** next to it is progress (occupied / moving), not a second stop |

Stations, west → east around the plant:

| Station | Where it is |
|---------|-------------|
| **Main West Brick-Plane** | Hairpin between Brick and Plane |
| **East Main Ext** | Main between Plane (102) and Barn (117) |
| **Main East** | Main south of the yard, approaching East End |
| **East Lead** | East End lead off 112 |
| **Main West** | Main West at East End (around-the-room from Brick) |
| **West Main Ext** | Main West between East End and Princess |
| **McKees Rocks** | Princess, north branch |
| **McKeesport** | Princess, south branch |

You can only start and stop at those eight. Yard tracks, W-1/W-2, and K-1/K-2
are not stations.

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
3. Pick the station block the engine is in, then the roster entry (e.g. 2091).
4. A neighbor block highlights. Answer **which way the train is facing** —
   toward that highlight, or the other way. That is polarity, not the route.
5. Accept length and speed factor if they look right.

The station label on **My Layout** should show the train name. If you lift the
train to another station by hand, register it again there.

---

## 4. Send it to one station (no saved route)

Use this when you just want “go to Main East.”

1. Click **Run Dispatch** so it is selected (**Setup Route** must be off).
2. On **My Layout**, click the **wide label** of the destination station.
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
2. On **My Layout**, click stations **in the order the train should visit
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

To send it the long way on purpose, put **Main West Brick-Plane** (and
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
| Register 2091 | **Setup Train in Section** → block → 2091 → facing |
| One destination | **Run Dispatch** → click destination label |
| Same trip every time | **Setup Route** → click stations in order → **Complete Route**; later **Run Route** → pick that route |
| Stop at every station | **Express Train** **off** |
| Skip intermediates | **Express Train** **on** |
| Tail hanging out of the station | **Dispatch Path must be clear** **off** before you click |
