# Project plan — HART next-gen panel

- **Owner:** lnevo
- **Status:** Active — phases 0–2 scaffolded on `main` ([lnevo/hart](https://github.com/lnevo/hart))
- **Date:** 2026-08-07
- **Layout name:** `hart`
- **Baseline:** `jmri/layouts/linear6/linear6.xml` (connectivity + positionability)

## Evidence

- linear6 is the live hand-tuned panel (MQTT switches 100–119, CP labels Brick/Plane/East End/Princess).
- linear6 was not a registered pipeline layout; no wiki SoR existed.
- Dispatcher review (2026-08-07): CP naming, OS purity, label hierarchy, prepare for signals later — **not** in v1 scope.

## Problem

Best geometry and live wiring live in an ad-hoc folder without a named layout project, naming contract, or version control — blocking clean multi-agent work and a signal-ready board.

## Non-goals (phases 0–2)

- Full Signal Mast Logic / ABS
- NX Entry/Exit rollout
- NextTrain / Google Sheets sync
- Mutating the live Pi load in place (hart is a new panel file; JMRI profile/tables stay)
- linear3-style resize / `fit_panel_*` / polish skew

## Outcomes

1. Registered layout `hart` with standard tree + README.
2. Panel derived from linear6 connectivity/positions; public names follow CP/OS contract.
3. Unused internal sensors removed from the hart panel (keep `ISCLOCKRUNNING` and anything still referenced).
4. Public git repo with branch conventions for parallel agents.
5. Wiki SoR + ADRs accepted for identity, naming, and JMRI config isolation.

## Decisions (locked 2026-08-07)

| ID | Decision |
|----|----------|
| U1 | Layout / project name = **hart** |
| U2 | JMRI configuration based on existing profile; **change only the layout panel** |
| U3 | **linear6** = connectivity + positionability source; geometry refined per railroad + dispatcher feedback |
| Scope | Phases **0–2** only |
| Git | Public repo; branching for multiple agents |

See ADRs 001–003.

## Unknowns remaining

| ID | Item | Owner |
|----|------|--------|
| U4 | Purge duplicate empty `<block>` rows (86 table vs 43 layoutblocks) in same pass as sensor purge? | Spike in phase 2 |
| U7 | Aspect system | Deferred past phase 2 |

## Phases

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 0 | Wiki SoR, ADRs, DoD | In progress |
| 1 | Scaffold `hart`, register paths, freeze baseline, bootstrap panel | In progress |
| 2 | Naming contract applied; unused internal sensors removed; OS audit notes | In progress |
| 3+ | Dark masts, NX, SML, NextTrain | Out of scope |

## Related

- ADRs: [`../decisions/`](../decisions/)
- Bootstrap: `jmri/scripts/bootstrap_hart_from_linear6.py`
- Panel: `jmri/layouts/hart/`
