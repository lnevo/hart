# Live status

Updated 2026-11-02. Dated history is in [`STATUS_LOG.md`](STATUS_LOG.md).

## Current state

- **Layout:** `hart`. Masts are stock Basic (ADR-011). The repo's `jmri/layouts/hart/output/tables.xml` is the master (ADR-008). Every host loads `preference:tables.xml` from `JMRI_UserFiles` (ADR-014).
- **JMRI:** production 5.16 on the Mac, Pi and Windows, the newest CATS 3.2 supports. Do not go past 5.16 until the CATS downloads page does.
- **Stock distributions:** JMRI 5.16 and CATS 3.2 run unpatched on all three hosts since 2026-10-31, under monitoring. If something breaks, compensate around them rather than changing them. JMRI Simple Server (port 2048) starts with each profile so CATS finds its operations server.
- **MQTT startup race:** Expect `ConcurrentModificationException` with `Can't subscribe` at startup: a JMRI race that drops the broker for a few seconds, then reconnects and resubscribes on its own (seen on the Mac 2026-10-31, on the Pi 2026-09-06). Retained messages alone trigger it, with no HART scripts running. Worry only if `Succeeded to reconnect` does not follow.
- **CATS load risk:** a turnout report during panel load can raise `NullPointerException ... requestLockClear` and kill the CATS event thread, freezing occupancy and turnout control. Do not move turnouts while CATS starts. If that error appears or occupancy stops updating, restart CATS. After CATS starts, use Appearance → Refresh Screen. Never use Refresh Layout: it can move points to a stale route.
- **Counts:** 45 masts (23 real, 22 virtual), 103 sections, 746 transits, 39 NX pairs, 38 SML sources with 98 destinations, 1,548 traininfo files.
- **Operations Pro files:** the repo is the master, in `jmri/layouts/hart/operations/` (ADR-015). Deploy installs them on every host and the repo wins, so run `make ops-pull` first to keep a Pi session. Out of service is tracked in the hart-ops car repository and published to STS and the roster; 10 cars are out.
- **Operations Pro rebuild (merged 2026-11-02, PR #120; deployed to the Mac, Pi and Windows the same day):** the folder was rebuilt from blank on 2026-11-02 with the operations-pro plugin, mapped from the STS session 3 end state: 13 locations, 6 trains (D749, D749 Return, NVL, CK1, STG-DEMMLER, STG-SCULLY), 112 schedule lines, 99 cars, 10 locomotives, two automations; the owner reviewed the decisions on 2026-11-02. Plan and decisions: [`docs/ops/OPSPRO_MAPPING.md`](../docs/ops/OPSPRO_MAPPING.md), [`docs/ops/OPSPRO_OPEN_QUESTIONS.md`](../docs/ops/OPSPRO_OPEN_QUESTIONS.md). All three hosts hold it, checksums matched after the deploy; the Pi's legacy files are kept in `archive/operations-pi-2026-11-02/`. What is still owed: [`docs/ops/OPSPRO_FOLLOWUP.md`](../docs/ops/OPSPRO_FOLLOWUP.md).
- **Host files:** CATS panels, launchers and logs live in `JMRI_UserFiles/cats/` on the Pi and Windows, plus TrainStat on the Pi. Deploy unpacks into a temporary folder (`/tmp`, `%TEMP%`) and removes it. Every profile sets `user-files` to `JMRI_UserFiles`, so that is where `preference:` resolves and where deploy writes. Run `make tables-pull` after a PanelPro Store.
- **JMRI scripts:** `signal_coordinator.py` and `panel_status.py` run from Start Up, `jmri_cmd_watcher.py` too on the Pi. A LogixNG in `tables.xml` calls `hide_cats_desk_windows.py`.
- **Desks:** CATS CTC `HOLD_ONLY` by default; USS is the alternate. Never both.
- **CATS panels:** `HART_Digicon.xml` is the Designer save; `wire_digicon.py` builds `HART_CTC.xml` and `HART_ABS.xml` (ADR-012).
- **Cars:** 99 in the repository and in the Operations roster on every host, 28 of them with no photo yet and unplaced (ADR-013). STS has 70, without those 28 or HART 1776.
- **STS:** runs from `external/sts-docker` with data in `external/sts-docker-data`; backups go only to `external/sts-docker-data/backups`. `~/sts` is frozen and unused.
- **STS to JMRI:** STS is the master of car positions, loads and final destinations, and refreshes JMRI Operations one way with the **Send Cars to JMRI** step or Operations button ([ADR-016](decisions/ADR-016-sts-refreshes-jmri-operations.md); [`docs/ops/STS_TO_JMRI.md`](../docs/ops/STS_TO_JMRI.md)). `sts_car_sync.py` is in JMRI's Start Up on the Pi and the Mac; The JMRI address and name map are on the plugin's Settings page (saved to `external/sts-docker-data/config/jmri_ops.json`; HART's copy in `jmri/layouts/hart/data/sts_jmri_ops_settings.json`). The generic plugins name no HART value: the track scale has a Settings page too, and its HART values come from a preset in the `hart_layout` plugin (`hart_presets.php`), under its saved file. HART's coke orders (the Replenish Coke Orders step, keeping COKE- orders) are plain `hart_layout` code.
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
- HART 1776 stays out of STS until its car card is generated. The 28 cars with no photo stay out too: no photo means no card, so they go in only after a photo.

## Future goals

- Measured speed profiles ([`projects/speedmatching.md`](projects/speedmatching.md)).
- Verify the stock bugs and send fixes upstream if they hold: the JMRI `MqttAdapter.messageArrived` listener race, plus the CATS items in [`CATS_OVERLAY_REVIEW.md`](../docs/ctc/CATS_OVERLAY_REVIEW.md). The JMRI fix is in `tools/jmri/patches` at `443b5f28~1`.
- Final cleanup epic: retire `~/sts`, `~/Desktop/HART`, the duplicates in `~/Documents` and the repo's `archive/`, leaving this repo as the one home ([ADR-007](decisions/ADR-007-repository-layout.md)). Undated on purpose. The `.any` track plans stay in `~/Documents`.
