# HART Railroad — CATS CTC Dispatcher Guide

**Publication:** DS-CATS-DISP · Rev A · Eff 2026-08-19  
**Railroad:** HART Railroad · Pittsburgh & Chartiers Valley Division · Neville Island Operations  
**Scope:** CATS Digicon panel (`HART_Master_CTC_hold.xml`), mouse dispatching in CTC mode

Welcome to the desk. This guide is for **being a dispatcher on the CATS panel** — how you
grant authority, line routes, and use fleeting, stacking, and call-on. It is **not** a
software manual (menus, install, Designer, MQTT). For that, see the CATS PDF in
`tools/cats/release3.2/catsManual.pdf` and [`HART_DIGICON_SYSTEM.md`](HART_DIGICON_SYSTEM.md).

**Do not duplicate the USS machine guide.** HART also has a stock JMRI CTC lever panel
(code buttons, N/L/R levers, 15 columns). That machine is documented separately:

→ [`jmri/layouts/hart/ctc/DISPATCHER_GUIDE.md`](../../jmri/layouts/hart/ctc/DISPATCHER_GUIDE.md) (DS-DISP)

Run **either** CATS CTC **or** the JMRI USS panel — never both. Both drive Hold on the
same masts. CATS ABS is a view-only mimic and is fine alongside either.

---

## 1. Reading the Digicon panel

The schematic runs **west → east** (left → right): Brick → Plane → Barn → East End →
Princess, with South Yard on the ladder and McKees Rocks / McKeesport at the east end.
It is an **interlocking diagram**, not a scale map.

| What you see | Meaning |
|--------------|---------|
| **Track color** | Occupancy (from JMRI/MQTT detectors) |
| **Green arrows** | Active route through that block, direction of travel |
| **Signal icon color** | Rough mirror of field aspect: idle (white/grey), yellow (approach), green (clear path), red (stop / blocked) |
| **White vs grey signal** | White = engineer sees a mast at that CP; grey = panel-only CP |
| **Switch alignment** | Normal vs reverse on the schematic (field feedback) |

On HART, **CATS grants routes and throws turnouts**; **JMRI Signal Logic (SML)** computes
aspects once a mast is released from Hold. You request permission; the plant decides
Clear vs Approach vs Stop from occupancy and points.

At session start, CTC homes are **Held** (Stop). A successful route **Unholds** the
entrance mast; SML then shows the best aspect the conditions allow.

---

## 2. Lining a route (the everyday move)

### Quick route — one plant, fixed alignment

Use when points are already lined and you only need the next interlocking step.

1. Confirm the **entrance block is unoccupied** and no conflicting route is active.
2. **Left-click** the **signal head** (not the mast base) at the CP where the train enters.
3. If accepted, the icon colors up and green arrows show the protected path to the **next
   CP** in that direction. Turnouts are **not** moved — the route follows whatever alignment
   the track already has.
4. To **take it back**, left-click the same icon again while it is green/yellow, or wait
   for the train to clear (sectional release frees blocks behind the train).

**Tip:** Click the lamp head; CATS hot zones are picky.

### Extended route (N/X) — multiple plants, CATS lines turnouts

Use when the move needs **turnouts thrown** across several control points (typical mainline
run: Brick → Plane → Barn → …).

1. **Right-click** the **entry** signal → **Set N/X Route** → **Accept**.
2. The entry icon **blinks** (entry/exit color) — CATS is waiting for the far end.
3. **Left-click** the **exit** signal. CATS picks a path (prefers main/normal alignments),
   waits for turnouts to prove unoccupied, throws points, then builds a chain of quick routes
   through every CP on the path.
4. To **shorten** the chain: left-click an intermediate CP (clears that leg) or right-click
   → **Cancel N/X Route** (drops that CP and everything beyond).

If creation fails, read the pop-up: no path, blockage, occupied block ahead of the entry
signal, or opposing route. Fix points/occupancy or cancel the conflict — do not hammer clicks.

---

## 3. When to use what

| Situation | Use |
|-----------|-----|
| Local move, points already set (e.g. yard lead already aligned) | **Quick route** (left-click entry) |
| Mainline move across named plants with turnouts to throw | **N/X route** (right-click Set N/X → left-click exit) |
| Same move needed **after** the first train clears, but path is blocked now | **Stack route** (below) |
| Second train following the same direction, close behind | **Fleeting** (below) — only after a route is **active** |
| Engine rejoining cars left on the main, or run-around finish | **Call-on** (below) or track authority on the fouling turnouts |
| Conflicting or unknown plant | **Nothing** — leave signals at Stop |

---

## 4. Route stacking

**Stacking** queues an N/X-style move that **cannot run yet** (block occupied, opposing
traffic, turnout under a train). When the blocking condition clears, CATS runs the deferred
route automatically — you do not have to hover over the panel.

**Procedure:** Same as N/X, but choose **Stack Route** on the entry signal menu, then
left-click the exit. Confirm the stack dialog. Repeat to queue more moves.

**Manage the queue:** Right-click any signal → **View/Change Stacked Routes**. The **top**
line is the one waiting for a clear path; delete or reorder from this dialog.

**Good HART examples:**

- NVL clears Princess; you stack the **return** move through 113 before the plant is free.
- D749 will need a **South Yard setout** right after clearing Barn — stack it while the
  train is still east of the plant.
- Opposing meets at East End: stack the second train’s route while the first occupies 111/112.

**Cautions:**

- Do not stack contradictory paths through the same plant.
- Stacked routes still respect occupancy — they run when clear, not on a timer.
- On large loops, extended-route search can get confused; keep stacks to sensible CP pairs.

---

## 5. Fleeting

**Fleeting** re-creates a route as sectional release drops signals behind a train, so a
**parade** of same-direction trains does not need a fresh click at every plant.

**Turn on:** Right-click a signal that **already has an active route** → **Turn on
Fleeting**. On an N/X chain, fleeting applies from that CP **through the rest of the chain**.

**Turn off:** Right-click → **Cancel Fleeting**, or left-click the CP as the train passes
(cancels fleeting and can drop the CP from an N/X chain).

**HART rule:** Fleeting is disabled until a route is **ACTIVE** — you cannot fleet an idle
signal.

**When to use:** D749 strings, CK1 coke moves, repeated NVL turns in the same direction.

**When not to use:** Any move where you may need to **snatch authority back** quickly,
opposing meets, or work that crosses the main at a plant you are fleeting through.

---

## 6. Call-on

**Call-on** (Return to Train) is a **one-move override**: permission to pass a Stop signal
into an **occupied** block ahead — typically to **rejoin cut-off cars** on the main after
a run-around or helper tie-on.

**Procedure:**

1. Line the **turnouts** for the join (you keep control; do not grant local switching unless
   that is your railroad’s rule).
2. Right-click the **entrance signal** → **Call-on** → **Accept**. The icon blinks; the
   field mast shows **Restricting** (flashing red / restrictive indication).

**CATS will offer call-on only when** (all must be true):

- The **immediate** block in front of the signal is **not** occupied.
- The **next** block **is** occupied (the cars or train you are joining).
- No track authority or out-of-service on those blocks.

**End call-on:** Cancel from the signal menu, or when the immediate block becomes occupied
(the engine entered the overlap).

**Alternatives:** Grant **track authority** on the fouling turnouts and let the crew
switch themselves; or line a quick route out to the main and **flag** the return (no CATS
feature — verbal permission).

---

## 7. Other dispatcher tools (brief)

| Tool | Mouse | Use |
|------|-------|-----|
| **Throw turnout** | Right-click switch → align Normal/Reverse | Local plant lining when not in a locked route |
| **Track authority** | Right-click track | Let crew move within limits without a signaled route |
| **Out of service** | Right-click track | Take a block off the board for maintenance |
| **Train label** | Drag label between blocks | Track identity when Train Tracker is off or wrong |
| **Yard ladder lamps** | Click S-1…S-5 buttons | Line South Yard ladder tracks (pairs with JMRI auto-routes) |

---

## 8. Rules of thumb (HART)

1. **One dispatcher, one CTC authority** — CATS CTC *or* JMRI USS, not both.
2. **Signals govern** — if the mast is Stop, the train stops. If CATS rejects a route, find
   occupancy, points, or an opposing reservation before overriding.
3. **Line switches before you expect diverging clears** — quick routes do not throw
   turnouts; N/X does.
4. **Do not move points under a train** — CATS waits on turnout safety delay; still check
   the schematic.
5. **Use stacking for choreography**, **fleeting for parades**, **call-on for joins** — not
   interchangeably.
6. **West Yard ladder (116 / 103) and South Yard Switch 104** are **yard
   territory** — no CTC homes. Westbound into Barn from the yard lead is the
   **T6** dwarf on the 117 plant. K-stub tracks are restricted speed beyond
   the dwarfs, prepared to stop.
7. **Refresh Screen** is safe after glitches; avoid **Refresh Layout** during ops (pushes
   panel state at JMRI).

---

## 9. Quick reference

| I want to… | Do this |
|------------|---------|
| Clear one plant, points already set | Left-click entry signal |
| Route Brick → Princess with turnouts | Right-click entry → Set N/X → left-click exit |
| Queue a move for when the plant clears | Right-click entry → Stack Route → left-click exit |
| Run several trains same way close together | Line route → right-click → Turn on Fleeting |
| Engine back onto cars on the main | Line turnouts → right-click → Call-on |
| Cancel everything at a CP | Left-click active signal, or Cancel N/X / Cancel Fleeting |
| See what is queued | View/Change Stacked Routes |

---

*Office of the Superintendent · Neville Island Operations · DS-CATS-DISP Rev A*
