# HART Railroad — CTC Machine Dispatcher Guide

**Publication:** DS-DISP · Rev A · Eff 2026-08-19
**Railroad:** HART Railroad · Pittsburgh & Chartiers Valley Division · Neville Island Operations
**Scope:** JMRI USS CTC machine (**USS CTC**), basic dispatching rules

Welcome to the desk. This machine is a model of a US&S Centralized Traffic
Control panel: you line switches and signals from here, and the interlocking
logic — not you — decides whether a signal can actually clear. Field signal
aspects are computed by JMRI signal logic (ABS rules behind your CTC
authority). You grant permission; the plant protects the railroad.

To **run a train automatically** between stations, use Dispatcher System, not
this machine: [`../dispatcher/DISPATCHER_GUIDE.md`](../dispatcher/DISPATCHER_GUIDE.md)
(DS-AUTO).

---

## 1. Reading the machine

The panel is **15 columns, west → east, left → right**, matching the
railroad: Brick → Plane → Barn → East End → Princess. Each column is one
**OS section** (interlocking plant) with, top to bottom:

- **Track diagram row** — OS lamp lights **red while a train occupies the
  plant**. Crossover columns have a second lamp on the lower track's bar.
  Small searchlight icons on the rails are the **CTC-held masts** for that
  column (Quaker Valley style): two-head homes and one-head dwarfs, facing
  the traffic they govern. They paint the field aspect (red at Hold/Stop,
  yellow Approach / Restricting, green Clear). Hover for the mast name.
  Switches **116** and **103** have no signal icons — those columns are
  switch-only.
- **Switch lever** (odd numbers 1–29) — points **N** (Normal/straight) or
  **R** (Reverse/diverging), with N/R correspondence indicators.
- **Signal lever** (even numbers 2–30) — three positions: **L**, **N**, **R** —
  with L / N / R indicator lamps above it.
- **Lock toggle** (Locked / Unlocked / Local) — releases the switch for
  hand operation by a field crew; the Unlocked lamp lights while released.
- **Code button** — nothing you set takes effect until you press it.

| Cols | Station | Lever (SW/SIG) | Plant |
|------|---------|----------------|-------|
| 1 | Brick | 1 / 2 | Switch 101 (yard exits W-1 / W-2) |
| 2 | Brick | 3 / 4 | Switch 100 |
| 3 | Plane | 5 / 6 | Switch 102 (main vs Scale) |
| 4 | Barn | 7 / 8 | Switch 117 crossover (OS 117 / 117b). One signal lever releases both tracks |
| 5 | Barn | 9 / — | Switch 116 (ladder, switch-only, defaults Local) |
| 6 | Barn | 11 / — | Switch 103 (ladder, switch-only, defaults Local) |
| 7–8 | East End | 13 / 14, 15 / 16 | Switches 107, 108 (ladder, switch-only) |
| 9 | East End | 17 / 18 | Switch 111 crossover (OS 111a / 111b) |
| 10 | East End | 19 / 20 | Switch 109 (ladder, switch-only) |
| 11 | East End | 21 / 22 | Switch 110 (ladder → East Lead; defaults Local) |
| 12 | East End | 23 / 24 | Switch 112 (East Lead vs Main East) |
| 13 | Princess | 25 / 26 | Switch 113 crossover (OS 113b / 113a) |
| 14 | Princess | 27 / 28 | Switch 114 (McKeesport vs K-2) |
| 15 | Princess | 29 / 30 | Switch 115 (McKees Rocks vs K-1) |

Below the columns: **Fleeting** toggle, **Reload CTC**, and **CTC Debug**
(leave the last two alone in normal operation).

---

## 2. Operating the machine

### Line a signal (grant a route)

1. Check the OS lamp is **dark** (plant unoccupied).
2. Set the **switch lever** for the route you want (N or R) and **press
   code**. Wait for the N or R indicator to light — that is field
   correspondence, the points actually moved. An unlit pair means the
   switch is still in motion or failed.
3. Move the **signal lever**: **R** for an **eastward** (rightward) move
   through the plant, **L** for a **westward** (leftward) move.
4. **Press code.** The machine checks traffic locking. If the route is
   valid, the signal indicator lights and the field mast is released — the
   signal system then shows the best aspect the track conditions allow
   (Clear, Approach, Medium Clear on a diverging route, Restricting from a
   dwarf). If the request conflicts with an opposing route or the points,
   the machine **rejects it** and the signal stays at Stop. That is the
   machine doing its job, not a fault.

### Take a signal away

Return the signal lever to **N** and press code. **Time locking** then runs:
the indicators go out of correspondence for a few seconds before the
signal is re-held at Stop. This delay is deliberate — it protects a train
that may have already accepted the signal. Do not re-line anything until
the indicators settle.

### Throw a switch

A switch lever is **locked while its signal lever is off N** — take the
signal away first, then line the points. This is correct USS behavior:
never move points under a cleared route.

### Fleeting

The **Fleeting** toggle keeps a lined route standing so following moves in
the same direction get successive signals without re-coding each one. Use
it for a parade of same-direction trains only; turn it off when done.
Never fleet a route you may need to take back quickly.

---

## 3. Basic dispatcher rules

1. **Signals govern.** A Stop signal means stop — you cannot talk a train
   past one. If a signal will not clear, find out why (occupancy, points,
   opposing route) before doing anything else.
2. **One dispatcher, one machine.** Never run this machine and the CATS
   CTC panel at the same time — both drive Hold on the same signals and
   will fight. (The CATS ABS panel is a view-only mimic and is fine.)
3. **Never move points under a train.** If the OS lamp is red, hands off
   that column's levers until it clears.
4. **Line switches first, signals second; code after every change.**
   Nothing happens until you press the code button — and wait for the
   indicator before you trust the field.
5. **Expect rejections.** Traffic locking refuses conflicting or
   improperly lined routes. Correct the points or wait for the opposing
   move; do not hammer the code button.
6. **Respect time locking.** After you take a signal away, wait out the
   release delay. Plan far enough ahead that you rarely need to snatch a
   signal back from an approaching train.
7. **Keep mainline columns Locked.** Switches **116, 103, and 110** boot
   **Local** so the yard crew can throw the ladder without a code. Re-lock
   a column only if you need to take it back from the desk. Other columns
   stay Locked unless you hand them to a crew — plant unoccupied, signals
   at Stop — and re-lock the moment they report clear. You have no route
   protection through an unlocked switch.
8. **Yard ladder is unsignaled.** Switches 116 and 103 have **no signal
   levers**. The westbound home into Barn from the yard lead is
   **117LB** on the 117 column. Switch 104 and the rest
   of the South Yard ladder are occupancy-only. The K-1 / K-2 stubs and
   yard tracks are restricted-speed territory beyond the dwarf.
9. **During an automated dispatch, hands off the throttle.** A phone
   throttle press on a dispatched locomotive flips its direction bit and
   the auto train will run the wrong way. Release the locomotive from
   WiThrottle before dispatching; if an auto train stalls, terminate the
   dispatch and re-dispatch — never nudge it.
10. **Log your railroad.** Note trains, routes granted, and anything
   abnormal (failed correspondence, unexpected occupancy). The next
   dispatcher inherits your plant exactly as you leave it.
11. **When in doubt, leave everything at Stop.** A red railroad is a safe
    railroad; sort the situation out before granting new authority.

---

## 4. Quick reference

| I want to… | Do this |
|------------|---------|
| Route a train east through a plant | Switch lever N/R → code → wait for indicator → signal lever **R** → code |
| Route a train west | Same, signal lever **L** |
| Cancel a signal | Signal lever **N** → code → wait out time locking |
| Throw a switch | Signal lever must be **N** first; then switch lever → code |
| Run several trains the same way | Line the route, turn **Fleeting** on; off when done |
| Signal won't clear | Check OS lamp, points correspondence, opposing route — the machine is protecting something |

**Machine on:** PanelPro **Tools ▸ CTC ▸ Run CTC Logic**. It does not
auto-start — until you run it, every lever and lamp shows "?" (sensors
UNKNOWN). Once started, most switch levers initialize **N**. Switches **100, 112,
114, and 115** rest Thrown in the field — run
`jmri/layouts/hart/scripts/ctc_default_reverse_levers.py` after CTC
starts (or add it as a PanelPro startup action after Run CTC Logic) so
those selectors sit at **R**, and lock toggles for **116, 103, and 110**
sit at **Local**. Reload CTC re-applies the same defaults.
The CTC-held masts go to Stop: that is the correct idle state. **Machine off:** there is no stop
command — quit and relaunch PanelPro without starting the runtime; masts
boot Unheld and the railroad runs as plain ABS. The **Reload CTC** button
on the panel re-reads the machine configuration in place after edits.
Panel file: `jmri/layouts/hart/ctc/GUIObjects.xml`; machine config lives
in `tables.xml` (`<ctcdata>`).

---

## Related — CATS Digicon panel

This guide covers the **USS lever machine** only. For the **CATS mouse panel**
(quick routes, N/X, stacking, fleeting, call-on), see
[`cats/docs/DISPATCHER_GUIDE_CTC.md`](../../../../cats/docs/DISPATCHER_GUIDE_CTC.md)
(DS-CATS-DISP). Do not run both panels as CTC authority at once.
