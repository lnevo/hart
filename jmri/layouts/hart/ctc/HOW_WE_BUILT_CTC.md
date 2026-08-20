# How We Built the HART CTC Panel

Short overview for clubs and operators asking how the Neville Island (HART) CTC
machine was implemented. For day-to-day dispatching, see
[`DISPATCHER_GUIDE.md`](DISPATCHER_GUIDE.md). For the separate CATS Digicon panel,
see [`cats/docs/HART_DIGICON_SYSTEM.md`](../../../../cats/docs/HART_DIGICON_SYSTEM.md).

---

## What we run

HART has **two** CTC-style interfaces over the same JMRI layout; run **one** at a
time, not both:

| Panel | Look & feel | How it was built |
|-------|-------------|------------------|
| **JMRI USS machine** (“Panel ”) | Classic lever machine + track diagram | **Programmatic** (scripts below) |
| **CATS Digicon** | Mouse/track-click CTC | Redrawn in **CATS Designer** (`cats/panels/`) |

This document focuses on the **JMRI USS** panel — the one that shows code buttons,
N/L/R levers, and the gold track board.

---

## Implementation in three layers

### 1. Interlocking columns (logic)

Python **Jython** scripts run **inside PanelPro** (Script Console or our
`jmri_cmd_watcher.py` automation channel). They call the same JMRI CTC factory
classes the **Tools → CTC** editor uses — we did **not** click through the GUI
for fifteen plants.

- Pilot (Brick + Plane): `jmri/layouts/hart/scripts/build_ctc_brick_plane.py`
- Full plant (15 columns, Barn inserted): `build_ctc_full_15col.py`

Each script defines O.S. sections (sensors, turnouts, signal masts, crossover vs.
switch), then runs **`Topology`** auto-generation so traffic-locking rules come from
the existing **Signal Mast Logic (SML)** graph. A few ladder entrances needed
hand-tuned TRL patches (`patch_ctc_locking.py`, `revert_barn_ladder_signals.py`).

Output lands in `tables.xml` (`<ctcdata>`) and is loaded on the layout Pi.

### 2. Track diagram (graphics)

The USS **track board** is **not** drawn by hand in Panel Editor. A standalone
**Python 3** generator writes Panel Editor XML:

- `jmri/layouts/hart/scripts/gen_ctc_track_plan.py`

It places turnout icons, approach lamps, yard ladders, and the retiled gold
background (modeled loosely on [Quaker Valley CTC](https://www.quaker-valley.com/CTC/QV_CTCnew.html)).
Custom thin-leg turnout GIFs live in `jmri/layouts/hart/ctc/icons/`. Regenerating
updates both `ctc/GUIObjects.xml` and the embedded panel in `tables.xml`.

### 3. Runtime glue (still Jython, but not “building the panel”)

Startup scripts on the Pi handle MQTT feedback, default lever positions, yard
ladder lock toggles, etc. (`ctc_default_reverse_levers.py`, `apply_maintain_mqtt.py`,
…). SML itself is maintained via Layout Editor **Discover** — CTC consumes it; it
does not replace it.

---

## FAQ — copy-paste replies

### 1) “You used AI to build the JMRI CTC panel? I’d be interested in hearing how you did that.”

**Reply:** Yes — we used Cursor AI agents heavily to write and iterate the **Jython
build scripts** and the **Python track-plan generator**, but the architecture is
deliberate: call JMRI’s own CTC APIs (`CtcManager`, `CodeButtonHandlerDataRoutines`,
`Topology`) instead of manual editor entry, then verify levers, code buttons, and
time locking on the live Pi. AI helped us move fast on XML, traffic-locking edge
cases, and docs; layout geography, signal naming, and ops sign-off stayed human.

### 2) “Did you do this using JPython or driving the GUI?”

**Reply:** **Jython inside PanelPro**, not GUI automation — scripts like
`build_ctc_full_15col.py` programmatically create all fifteen O.S. columns and
auto-generate traffic locking from SML, the same path the CTC editor’s “Generate”
button uses. The **track diagram** is separate offline **Python 3** (`gen_ctc_track_plan.py`)
that emits Panel Editor XML; we never drove the CTC or Panel Editor with simulated
mouse clicks.

### 3) “How much did AI help build it out?”

**Reply:** AI was a **major accelerator** for scripting, config iteration, and
debugging (especially TRL/SML interactions and Barn ladder exceptions), but it
didn’t “draw the panel” in one shot — we still defined the plant column-by-column,
ran everything against real hardware, and reworked geometry many times (see
`wiki/STATUS.md` track-plan v2→v8 notes). Without programmatic generation, fifteen
columns would have been painful even with AI; with it, AI made the approach practical.

---

## If you want to try something similar

1. Freeze **connectivity and SML** on a Layout Editor panel first (ours came from
   the `hart` / linear6 baseline).
2. Prototype **one interlocking** with a small Jython script (our Brick/Plane pilot).
3. Use **`Topology`** for TRL; only hand-patch where yard ladders or crossovers
   need exceptions.
4. Generate the **USS graphics** separately so logic and art can rev independently.
5. Test on hardware: code button, TWOSENSOR feedback, time locking, and default
   lever positions (`ctc_default_reverse_levers.py`).

Scripts and repo copies: `jmri/layouts/hart/scripts/`, `jmri/layouts/hart/ctc/`,
`jmri/layouts/hart/output/tables.xml`.
