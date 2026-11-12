# ADR-020 — Live STS runs on the Pi

- **Status:** Accepted. Builds on ADR-016.
- **Date:** 2026-11-11
- **Deciders:** lnevo

## Context

The live STS ran in Docker on the Mac (10.0.0.53:8980), so it was there only when the Mac was on, and throttle phones on the `RPi-JMRI` Wi-Fi could not reach it. The Pi (Pi 5, 8 GB) is always on, already holds the broker and the live JMRI, and had the room.

## Decision

1. The live STS runs on the Pi at `http://RPi-JMRI.local:8980/sts/`, from `~/sts/sts-docker` (branch `active`), `~/sts/sts-plugins` (`main`) and data in `~/sts/sts-docker-data` (database, backups, `Rolling Stock photos`, config). It uses sts-docker's release stack (`docker-compose.release.yml`): the plugins are built into the image and only data folders are mounted. Both containers restart with the Pi.
2. The Pi's code changes only by a `git pull` of both repos and a rebuild (`tools/hosts/pi_sts_update.sh`). Nothing is copied into a running container on the Pi, and the sts-helpers do not run there.
3. Content is prepared and tested on the Mac, whose stacks stay: 8980 is the Mac's working copy and 8981 the sandbox. Prepared data reaches the Pi as an STS backup restored there. The Pi's database is the master of a session.
4. The Mac's `jmri_ops` setting points at the Mac's own JMRI (`host.docker.internal:12080`), so a Send Cars from the Mac never touches the layout's Operations roster. The Pi's points at `10.0.0.150:12080`, as in `jmri/layouts/hart/data/sts_jmri_ops_settings.json`.
5. `lnevo/sts-plugins` is public, so the Pi pulls both repos over HTTPS without a key.
6. The MT300 (10.0.0.60) lets `RPi-JMRI` clients reach 10.0.0.150 on TCP 8980, in its `Allow-JMRI-to-house` rule, with a `10.42.0.2:8980` forward like JMRI's.

## Consequences

- The Pi started from the session 5 checkpoint `hart_session_post5` (70 cars) plus the 10 CSX hoppers intook on 2026-11-08, placed empty on K-1 at Shenango Coke Works (`SHEN-COKE-SHIPPING`).
- `localhost:8980` is now the Mac copy, which is what the STS tools and tests reach by default. Its health check reports `stack: uat` (`dev` until sts-docker #18); the Pi's release stack reports `live` (sts-docker #16). Agents need approval per write on `live`; on `uat` the owner's request covers writes, with restores, wipes and resets confirmed first. Live work sets `STS_API_URL=http://RPi-JMRI.local:8980/sts/api/v1` for that job only; it is never a session-wide default, so a test or prep script cannot write to the live database by accident.
- Back up live sessions on the Pi; its backups folder is `~/sts/sts-docker-data/backups`. The Mac's backups folder no longer follows the live railroad. `make sts-pull` (`tools/hosts/pi_sts_pull_backups.sh`) copies the Pi's backups and a full database dump to `external/sts-docker-data/pi/` on the Mac, so the live data is not only on the SD card; run it after each session.
- The Pi's userland is 32-bit (`armhf`) on a 64-bit kernel, so apt's Docker is 32-bit, and MariaDB publishes no 32-bit ARM image. The Pi runs Docker's static 64-bit binaries instead (`tools/hosts/pi_docker_static.sh`, which also updates them; `apt upgrade` does not). They need no 64-bit libraries, so the 32-bit system is untouched, and the official images run as arm64 with Docker's normal seccomp filter. Debian multiarch was rejected: its 64-bit `libc6` must match Raspberry Pi's `+rpt` build exactly.
- The Pi runs JMRI, Mosquitto, Apache/PHP and MariaDB. Watch its load during sessions; a rebuild loads it heavily for some minutes, so do not run one while the owner is operating.

## Amendment 2026-11-11: production, development and test

- **Production** is the Pi: STS, JMRI and the mimic inside JMRI. Operators use only the Pi.
- **Development** is the owner's, on the Mac interfaces, started only for pre-deployment testing: the Mac STS (`docker start sts-docker-db-1 sts-docker-web-1`), the website preview (`./www/scripts/serve_portal.sh`, http://127.0.0.1:8760/www/) and the Mac mimic. None start at login: the `com.hart.ops-portal` and `com.hart.mqtt-mimic` launch agents are disabled and the Mac STS containers are stopped.
- **Agents test in sandboxes**: the STS sandbox stack (8981, `bin/sandbox_baseline.sh` in sts-docker) and throwaway copies, never the Pi and not the owner's Mac interfaces unless asked.

## Amendment 2026-11-12: approved in development before production

- **Every STS change is approved by the owner in development before it reaches production.** That covers code (sts-docker, sts-plugins), workflows, and data changes such as shipments, locations, car records and waybills. The order is sandbox (agent tests), then development (the owner reviews and approves), then production.
- **Before building a change for production**, refresh the Mac STS from the Pi: `make sts-pull`, then load the newest `external/sts-docker-data/pi/db/` dump into the Mac database (dump the Mac database to its backups folder first) and copy the Pi's active workflow into `external/sts-docker-data/backups/session_editor/`. The Mac then matches the Pi.
- **Apply the change to development the way it will go to production**: the same commit for code (rebuild the Mac image from it), the same API calls or script for data. Tell the owner what to look at, and wait for an approval that names development. Starting the Mac STS for this review is part of the rule. Dev and the sandboxes are shut down when not in use: stop the Mac STS once the change is in production, and remove sandbox stacks after their tests.
- **Then production**: `tools/hosts/pi_sts_update.sh` only for a commit the Mac ran during the review, and data writes on the Pi only with the per-write approval that already applies to `live`, after a Pi backup.
- The 2026-11-12 coal and coke change (sts-docker #17, the Coal Shenango workflow section) went from the sandbox straight to the Pi. The Mac was refreshed from the Pi afterwards and matched it; this amendment is the response.
- Landmine: the Mac database lives in a macOS folder (`external/sts-docker-data/database/docker/sts/db`, `lower_case_table_names=2`). Dropping and recreating the job tables (`CK1`, ...) there can leave an orphaned entry that refuses `CREATE TABLE` with "Table 'ck1' already exists". The fix is a fresh data folder: stop the stack, move `db` aside, start it, and load the dump.

## Amendment 2026-11-12: development is UAT

- **The owner's Mac environment is user acceptance testing (UAT), not development.** It is where the owner accepts a change against the same data and the same MQTT broker as production, and UAT commonly shares data with prod. The Mac STS reports `stack: uat` (sts-docker #18, plugin 0.2.1); the write rule is unchanged from what `dev` had. "Development" and "dev" in the amendments above mean UAT.
- **One broker for every client.** The Mac and Windows tools talk to the Pi's broker, so several clients control the same layout; that is the point of MQTT here. The LCOS mimic publishing test feedback on that broker is accepted: it is for showing the layout working while it is powered off, and live sessions use direct mode instead of faked sensors. A separate broker is only for agents' sandboxes.
