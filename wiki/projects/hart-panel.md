# Project plan — HART next-gen panel

- **Owner:** lnevo
- **Status:** Active — live layout is past phases 0–2 (SML, CATS, USS, Dispatcher System)
- **Date:** 2026-08-07 (scaffold); **refreshed 2026-08-22**
- **Layout name:** `hart`
- **Baseline:** `jmri/layouts/linear6/linear6.xml` (connectivity + positionability)

## Evidence

- linear6 was the live hand-tuned panel (MQTT switches 100–119, CP labels Brick/Plane/East End/Princess).
- hart forked that geometry; it did **not** re-run AnyRail → Excel → blocked panel.
- Live SoR: [`../STATUS.md`](../STATUS.md) · Digicon: [`../../cats/docs/HART_DIGICON_SYSTEM.md`](../../cats/docs/HART_DIGICON_SYSTEM.md)

## Problem (original)

Best geometry and live wiring lived in an ad-hoc folder without a named layout project, naming contract, or version control.

## Non-goals that still hold

- NextTrain / Google Sheets — **abandoned**; not a HART desk
- Mutating Pi `tables.xml` from a CATS Store
- linear3-style resize / `fit_panel_*` / polish skew
- Merging AnyRail `ISIS200` block-boundary NX into live mast `ISNX:*` (HART NX is mast-only)

## Outcomes (phases 0–2) — done

1. Registered layout `hart` with standard tree + README.
2. Panel derived from linear6 connectivity/positions; public names follow CP/OS + [ADR-005](../decisions/ADR-005-public-equipment-names.md).
3. Public git repo with branch conventions for parallel agents.
4. Wiki SoR + ADRs for identity, naming, and JMRI config isolation.

## What landed after phase 2

Native SML (93 dests: 91 Layout Editor + 2 manual Princess), CATS CTC + ABS HOLD_ONLY, USS 15-column machine, Dispatcher System Stage 1 (91 sections / 688 transits / 1508 traininfo; all 22 stations are origins and destinations, including S-1…S-5). Load `jmri/layouts/hart/output/hart_prod.xml`; writable source `tables/new_tables.xml`.

## Remaining (railroad)

| Item | Notes |
|------|--------|
| Measured speed profiles | Synthetic 10-step / 400 mm/s on every roster loco — [`speedmatching.md`](speedmatching.md) |
| Dispatcher S-1…S-5 platforms | Done 2026-08-22 — hidden throats + Stage 1; 62 inbound traininfo each |
| First-registration facing invert | Overlay live; [JMRI#15407](https://github.com/JMRI/JMRI/issues/15407) open; [PR#15408](https://github.com/JMRI/JMRI/pull/15408) closed pending more testing |
| END_BUMPER far-slot hack | Keep until a real facing-block fix; still needed for W-1/W-2/K-1/K-2/EH |
| Node 13 occupancy walk-down | Done — 1301=OS 11 (118), 1304=EH-3, 1305=EH-2, 1306=EH-1, 1307=OS 9 (119); EH-1↔EH-3 swap stuck |

## Decisions (locked 2026-08-07)

| ID | Decision |
|----|----------|
| U1 | Layout / project name = **hart** |
| U2 | JMRI configuration based on existing profile; **change only the layout panel** (later: tables bundle is `output/tables.xml`) |
| U3 | **linear6** = connectivity + positionability source; geometry refined per railroad + dispatcher feedback |
| Git | Public repo; branching for multiple agents |

See ADRs 001–005.

## Phases

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 0 | Wiki SoR, ADRs, DoD | Done |
| 1 | Scaffold `hart`, register paths, freeze baseline, bootstrap panel | Done |
| 2 | Naming contract; unused internal sensors; OS audit notes | Done |
| 3+ | Dark masts, NX, SML | SML + mast NX done; NextTrain abandoned |

## Related

- ADRs: [`../decisions/`](../decisions/)
- Bootstrap: `jmri/scripts/bootstrap_hart_from_linear6.py`
- Panel: `jmri/layouts/hart/`
