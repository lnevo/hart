# Live status

Updated 2026-10-31. Dated history is in [`STATUS_LOG.md`](STATUS_LOG.md).

## Current state

- **Layout:** `hart`. Masts are stock Basic (ADR-011). JMRI loads `jmri/layouts/hart/output/tables.xml` (ADR-008).
- **Counts:** 45 masts (23 real, 22 virtual), 103 sections, 746 transits, 39 NX pairs, 38 SML sources with 98 destinations, 1,548 traininfo files.
- **Desks:** CATS CTC `HOLD_ONLY` by default; USS is the alternate. Never both.
- **CATS panels:** `HART_Digicon.xml` is the Designer save; `wire_digicon.py` builds `HART_CTC.xml` and `HART_ABS.xml` (ADR-012).
- **Cars:** 98 in the roster, 28 of them with no photo yet (ADR-013).
- **Website:** public at www.hartrailroad.com from `www/`.
- **Build:** helix complete. Main level resumes after Thanksgiving.

## Owed

Deferred by the owner on 2026-10-31; none of these is urgent.

- Deploy `sync_hart_package.sh --all` when the hosts are online. Until then the Pi and Windows run the old panels, and the desks have no Basic aspect mapping there.
- Railroad test of Basic signals: force a real Stop and read back Approach, Clear, Clear, in both directions and through a diverging route.
- STS staging for the 2026-11-08 operating session. STS has to be running, and the owner starts it.

## Pending

- CATS yard ladder buttons: decide whether to restore the 10 lamp buttons to the desks. They have been missing since the 2026-08-26 promotion; the Layout Editor lamps, routes and internal turnouts are live and unaffected. Hold until the ADR-012 desks are deployed and proven on the railroad. Until then, leave `add_yard_ladder_buttons.py` alone and do not re-run it. `DISPATCHER_GUIDE_CTC.md` and `HART_DIGICON_SYSTEM.md` still describe the buttons on the desks.

## Next

- Car workflow is ready ([`pipelines/car-workflow.md`](pipelines/car-workflow.md), ADR-013). Add the new photos with `bin/cars intake`.
- Later: resolve the differences `bin/cars compare` reports, starting with the 18 cars missing from the Pi's roster, and send corrections to existing cars through to STS and Operations Pro.

## Future goals

- Measured speed profiles ([`projects/speedmatching.md`](projects/speedmatching.md)).
- Agent skills and MCPs ([`projects/agent-skills-and-mcps.md`](projects/agent-skills-and-mcps.md)).
