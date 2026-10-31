# Live status

Updated 2026-10-31. Dated history is in [`STATUS_LOG.md`](STATUS_LOG.md).

## Current state

- **Layout:** `hart`. Masts are stock Basic (ADR-011). JMRI loads `jmri/layouts/hart/output/tables.xml` (ADR-008).
- **Counts:** 45 masts (23 real, 22 virtual), 103 sections, 746 transits, 39 NX pairs, 38 SML sources with 98 destinations, 1,548 traininfo files.
- **Desks:** CATS CTC `HOLD_ONLY` by default; USS is the alternate. Never both.
- **CATS panels:** `HART_Digicon.xml` is the Designer save; `wire_digicon.py` builds `HART_CTC.xml` and `HART_ABS.xml` (ADR-012).
- **Website:** public at www.hartrailroad.com from `www/`.
- **Build:** helix complete. Main level resumes after Thanksgiving.

## Owed

Deferred by the owner on 2026-10-31; none of these is urgent.

- Deploy `sync_hart_package.sh --all` when the hosts are online. Until then the Pi and Windows run the old panels, and the desks have no Basic aspect mapping there.
- Railroad test of Basic signals: force a real Stop and read back Approach, Clear, Clear, in both directions and through a diverging route.
- STS staging for the 2026-11-08 operating session. STS has to be running, and the owner starts it.

## Next

- Car workflow: reconcile Operations Pro, STS and hart-ops, then define one way to add and edit a car (ADR-007, D11/P3a).

## Future goals

- Measured speed profiles ([`projects/speedmatching.md`](projects/speedmatching.md)).
- Agent skills and MCPs ([`projects/agent-skills-and-mcps.md`](projects/agent-skills-and-mcps.md)).
