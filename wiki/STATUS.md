# Live status

Updated 2026-10-31. Dated history is in [`STATUS_LOG.md`](STATUS_LOG.md).

## Current state

- **Layout:** `hart`. Masts are stock Basic (ADR-011). JMRI loads `jmri/layouts/hart/output/tables.xml` (ADR-008).
- **Counts:** 45 masts (23 real, 22 virtual), 103 sections, 746 transits, 39 NX pairs, 38 SML sources with 98 destinations, 1,548 traininfo files.
- **Desks:** CATS CTC `HOLD_ONLY` by default; USS is the alternate. Never both.
- **CATS panels:** `HART_Digicon.xml` is the Designer save; `wire_digicon.py` builds `HART_CTC.xml` and `HART_ABS.xml` (ADR-012).
- **Cars:** 99 in the repository and on the Pi, 28 of them with no photo yet (ADR-013). STS has 70, without those 28 or HART 1776.
- **Website:** public at www.hartrailroad.com from `www/`.
- **Repo gates:** `main` is protected on GitHub, CI runs `tools/check.sh` on PRs, and `.claude/hooks/main_guard.py` guards every session, including against commits on `main` and admin merges.
- **Build:** helix complete. Main level resumes after Thanksgiving.

## Owed

Deferred by the owner on 2026-10-31; none of these is urgent.

- STS staging for the 2026-11-08 operating session. STS has to be running, and the owner starts it.

## In progress

- 3D station maps: multi-colour fascia plates that hold Touch Toggles ([`docs/benchwork/station_maps_3d/`](../docs/benchwork/station_maps_3d/README.md)). Barn is the first and only map modelled so far. Its plate outline and thickness are placeholders until the frame is measured, and the toggle pocket depth is a guess.

## Next

- Car workflow is ready ([`pipelines/car-workflow.md`](pipelines/car-workflow.md), ADR-013). Add the new photos with `bin/cars intake`.
- Later: bring HART 1776 and the 28 cars with no photo into STS, and replace the assumed 40 ft length on the 9 cars added to the Pi on 2026-10-31.

## Future goals

- Measured speed profiles ([`projects/speedmatching.md`](projects/speedmatching.md)).
