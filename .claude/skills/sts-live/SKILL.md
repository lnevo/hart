---
name: sts-live
description: Use when an STS change (sts-docker or sts-plugins code, a workflow, or data such as shipments, locations, cars or waybills) must reach the live STS on the Pi, when asked to run pi_sts_update.sh or make sts-pull, when the Mac STS (UAT) must be refreshed from the Pi, or when a job needs the live STS API.
---

# Live STS on the Pi

The live STS runs on the Pi at `http://RPi-JMRI.local:8980/sts/` (ADR-020). Its database is the master of a session. The Mac copy at `localhost:8980` is UAT, where the owner accepts a change; 8981 is the agents' sandbox. `sts_health` names the stack: `live`, `uat` or `sandbox`.

## The order of every change

Sandbox (agent tests), then UAT (the owner approves), then live. This covers code, workflows and data alike (ADR-020 amendment 2026-11-12).

1. **Sandbox.** Test on 8981 (`bin/sandbox_baseline.sh` in sts-docker) or a throwaway copy. Remove the sandbox stack afterwards.
2. **Refresh UAT from the Pi** before building for production:
   - `make sts-pull` copies the Pi's backups and a full database dump to `external/sts-docker-data/pi/` (it only reads on the Pi).
   - Dump the Mac database to its backups folder, then load the newest `external/sts-docker-data/pi/db/` dump into it.
   - Copy the Pi's active workflow into `external/sts-docker-data/backups/session_editor/`.
3. **Apply to UAT the way it will go live**: the same commit for code (rebuild the Mac image from it), the same API calls or script for data. Start the Mac STS for this (`docker start sts-docker-db-1 sts-docker-web-1`). Tell the owner what to look at and wait for an approval that names UAT.
4. **Live**:
   - Code: `tools/hosts/pi_sts_update.sh`, only for a commit the Mac ran during the review. It does a `git pull --ff-only` of `~/sts/sts-docker` (branch `active`) and `~/sts/sts-plugins` (`main`) on the Pi, then rebuilds the release stack. `--status` shows commits and containers only. Nothing is ever copied into a running container.
   - Data: take a Pi backup first, then write with the owner's yes for each write. Set `STS_API_URL=http://RPi-JMRI.local:8980/sts/api/v1` and `STS_EXPECT_STACK=live` for that one job only, never as a session default, so no test or prep script reaches the live database. The sts-helpers clients expect `uat` unless told otherwise and refuse a write to `live` without `STS_EXPECT_STACK=live`; simulations and sweeps run only on the sandbox.
5. **Shut down** the Mac STS once the change is live.

## Before you run it

- Do not rebuild on the Pi while the owner is operating. A rebuild loads the Pi (JMRI, Mosquitto, Apache and MariaDB run there) for some minutes.
- The sts-helpers never run on the Pi.
- Docker on the Pi comes from Docker's apt repository on 64-bit trixie since 2026-11-23 (ADR-032); `apt upgrade` updates it.

## After a session

Run `make sts-pull` so the live data is not only on the SD card. Dumps are plain SQL: to look at one, load it into the sandbox, never into the Pi.

## Landmine

The Mac database lives in a macOS folder (`lower_case_table_names=2`). Dropping and recreating job tables there can leave "Table 'ck1' already exists". Fix: stop the stack, move `db` aside, start it, load the dump.

## Report

Name the stack each step ran on, the commit or calls applied, the owner's UAT approval, and the Pi backup taken before any live write.

## Sources

- `wiki/decisions/ADR-020-live-sts-on-the-pi.md` (with the 2026-11-11 and 2026-11-12 amendments)
- `tools/hosts/pi_sts_update.sh`, `tools/hosts/pi_sts_pull_backups.sh`, `wiki/decisions/ADR-032-pi-os-trixie-64-bit.md`
- The `sts:sts-api` skill for the operating cycle and API details
