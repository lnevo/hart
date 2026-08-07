# ADR-004 — CATS as Digicon-style CTC (alongside JMRI panel)

- **Status:** Accepted
- **Date:** 2026-08-07
- **Deciders:** lnevo
- **Sources:** [CATS home](http://cats4ctc.wikidot.com/), [downloads](http://cats4ctc.wikidot.com/main:downloads), [user guides](http://cats4ctc.wikidot.com/main:userguides)

## Context

HART has a Layout Editor panel (`hart_prod.xml`) with MQTT occupancy and turnouts, plus interest in NextTrain. [CATS](http://cats4ctc.wikidot.com/) provides Digicon-inspired CTC interlocking on top of JMRI without importing Layout Editor geometry.

## Decision

1. **JMRI version:** use the **current** layout host build. Panel XML reports **5.15.4plus** — within **CATS 3.2** support (**JMRI 4.24–5.16**). Re-check downloads before any JMRI upgrade past 5.16.
2. **CATS** is the live **CTC command authority** for turnouts/routes during CTC sessions.
3. Keep **`hart_prod.xml` Layout Editor** as the hardware/monitor panel (MQTT devices, block colors, field labels).
4. **Redraw** the railroad in CATS **Designer** under `cats/panels/`; bind the **same JMRI names** (`OS 100 (Brick)`, `M2T408` / Switch 100, occupancy `Block 4-2`, …).
5. **First live plant: Brick** (OS 100 / OS 101), then Plane → east.
6. NextTrain and LE click-to-throw stay **view / local** during CATS CTC sessions (do not dual-command).
7. **Do not save** CATS-created SignalHead/Mast objects into JMRI tables (load-crash risk per Designer manual).

## Consequences

- Device catalog CSV is exported from hart for Designer binding (`cats/data/jmri_devices.csv`).
- Designer work starts at Brick (`cats/docs/BRICK_BINDINGS.md`).
- JMRI upgrades past 5.16 require a new CATS release check before cutting over.
- NextTrain remains a parallel schematic product; it is not fed by CATS XML.

## Alternatives considered

- JMRI SSL/SML only — rejected as primary CTC look-and-feel (Digicon is the goal).
- NextTrain as CTC command authority — rejected; CATS throws switches in CTC.
- Import LE into Designer — not supported; redraw required.
