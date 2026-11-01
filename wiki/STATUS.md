# Live status

Updated 2026-10-31. Dated history is in [`STATUS_LOG.md`](STATUS_LOG.md).

## Current state

- **Layout:** `hart`. Masts are stock Basic (ADR-011). JMRI loads `jmri/layouts/hart/output/tables.xml` (ADR-008).
- **JMRI:** production 5.16 on the Mac, Pi and Windows, the newest CATS 3.2 supports. Do not go past 5.16 until the CATS downloads page does.
- **Stock distributions:** JMRI 5.16 and CATS 3.2 run unpatched on all three hosts since 2026-10-31, under monitoring. If something breaks, compensate around them rather than changing them. JMRI Simple Server (port 2048) starts with each profile so CATS finds its operations server.
- **MQTT startup race:** Expect `ConcurrentModificationException` with `Can't subscribe` at startup: a JMRI race that drops the broker for a few seconds, then reconnects and resubscribes on its own (seen on the Mac 2026-10-31, on the Pi 2026-09-06). Retained messages alone trigger it, with no HART scripts running. Worry only if `Succeeded to reconnect` does not follow.
- **CATS load risk:** a turnout report during panel load can raise `NullPointerException ... requestLockClear` and kill the CATS event thread, freezing occupancy and turnout control. Do not move turnouts while CATS starts. If that error appears or occupancy stops updating, restart CATS.
- **Counts:** 45 masts (23 real, 22 virtual), 103 sections, 746 transits, 39 NX pairs, 38 SML sources with 98 destinations, 1,548 traininfo files.
- **Desks:** CATS CTC `HOLD_ONLY` by default; USS is the alternate. Never both.
- **CATS panels:** `HART_Digicon.xml` is the Designer save; `wire_digicon.py` builds `HART_CTC.xml` and `HART_ABS.xml` (ADR-012).
- **Cars:** 99 in the repository and on the Pi, 28 of them with no photo yet (ADR-013). STS has 70, without those 28 or HART 1776.
- **STS:** runs from `external/sts-docker` with data in `external/sts-docker-data`; backups go only to `external/sts-docker-data/backups`. `~/sts` is frozen and unused.
- **Website:** public at www.hartrailroad.com from `www/`.
- **Repo gates:** `main` is protected on GitHub, CI runs `tools/check.sh` on PRs, and `.claude/hooks/main_guard.py` guards every session, including against commits on `main` and admin merges.
- **Build:** helix complete. Main level resumes after Thanksgiving.

## Owed

Deferred by the owner on 2026-10-31; none of these is urgent.

- STS staging for the 2026-11-08 operating session. STS has to be running, and the owner starts it.

## In progress

- 3D station maps: multi-colour fascia plates that hold Touch Toggles ([`docs/benchwork/station_maps_3d/`](../docs/benchwork/station_maps_3d/README.md)). Barn is the first and only map modelled so far. Its plate outline and thickness are placeholders until the frame is measured, and the toggle pocket depth is a guess.

## Next

- Verify the stock bugs and send fixes upstream if they hold: JMRI `MqttAdapter.messageArrived` copies its listener map unsynchronised, and CATS `PtsVitalLogic.setSelectedTrack` crashes the unguarded `AsyncDelayLine` thread. The removed overlays show both fixes: `tools/jmri/patches` at `443b5f28~1`, `tools/cats/patches` at `443b5f28`.
- Car workflow is ready ([`pipelines/car-workflow.md`](pipelines/car-workflow.md), ADR-013). Add the new photos with `bin/cars intake`.
- HART 1776 stays out of STS until its car card is generated. The 28 cars with no photo stay out too: no photo means no card, so they go in only after a photo.
- The 9 cars added to the Pi on 2026-10-31 stay at 40 ft (owner's decision). All 70 STS cars match the repository's ids, types and lengths, so STS needs no edits.

## Future goals

- Measured speed profiles ([`projects/speedmatching.md`](projects/speedmatching.md)).
- Final cleanup epic: retire `~/sts`, `~/Desktop/HART`, the duplicates in `~/Documents` and the repo's `archive/`, leaving this repo as the one home ([ADR-007](decisions/ADR-007-repository-layout.md)). Undated on purpose. The `.any` track plans stay in `~/Documents`.
