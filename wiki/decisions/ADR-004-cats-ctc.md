# ADR-004 — CATS as Digicon-style CTC (alongside JMRI panel)

- **Status:** Proposed (implementing scaffold; await JMRI version + authority choice)
- **Date:** 2026-08-07
- **Deciders:** lnevo (pending confirmation)
- **Sources:** [CATS home](http://cats4ctc.wikidot.com/), [downloads](http://cats4ctc.wikidot.com/main:downloads), [user guides](http://cats4ctc.wikidot.com/main:userguides)

## Context

HART has a Layout Editor panel (`hart_prod.xml`) with MQTT occupancy and turnouts, plus interest in NextTrain. [CATS](http://cats4ctc.wikidot.com/) provides Digicon-inspired CTC interlocking on top of JMRI without importing Layout Editor geometry.

## Decision (proposed default)

1. **Adopt CATS v3.2** as the CTC interlocking / Digicon dispatcher UI path when JMRI is **≤ 5.16** ([downloads matrix](http://cats4ctc.wikidot.com/main:downloads)).
2. Keep **`hart_prod.xml` Layout Editor** as the hardware/monitor panel (MQTT devices, block colors, field labels).
3. **Redraw** the railroad in CATS **Designer** as a separate CTC schematic XML under `cats/`; bind the **same JMRI user names** (`OS 100 (Brick)`, `Switch 100`, occupancy `Block 4-2`, …).
4. **One live command authority** for turnouts/routes: prefer **CATS** for CTC sessions; NextTrain and LE remain view / local until explicitly gated. Do not run LE Signal Mast Logic and CATS interlocking on the same masts.
5. **Do not save** CATS-created SignalHead/Mast objects into JMRI tables (load-crash risk per Designer manual).

## Consequences

- Device catalog CSV is exported from hart for Designer binding (`cats/data/jmri_devices.csv`).
- Designer panel files live in `cats/panels/` (start with Brick stub).
- JMRI upgrades past 5.16 require a new CATS release check before cutting over.
- NextTrain remains a parallel schematic product; it is not fed by CATS XML.

## Alternatives considered

- JMRI SSL/SML only — rejected as primary CTC look-and-feel (Digicon is the goal).
- NextTrain as sole dispatcher — keep for ops UI; CATS owns interlocking when enabled.
- Import LE into Designer — not supported; redraw required.

## Open confirmations

- [ ] JMRI version on layout host
- [ ] Confirm CATS (not NextTrain) throws switches in CTC sessions
- [ ] First plant to wire live: Brick (default)
