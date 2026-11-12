# ADR-020 — Live STS runs on the Pi

- **Status:** Accepted. Builds on ADR-016.
- **Date:** 2026-11-11
- **Deciders:** lnevo

## Context

The live STS ran in Docker on the Mac (10.0.0.53:8980), so it was there only when the Mac was on, and throttle phones on the `RPi-JMRI` Wi-Fi could not reach it. The Pi (Pi 5, 8 GB) is always on, already holds the broker and the live JMRI, and had the room.

## Decision

1. The live STS runs on the Pi at `http://10.0.0.150:8980/sts/`, from `~/sts/sts-docker` (branch `active`), `~/sts/sts-plugins` (`main`) and data in `~/sts/sts-docker-data` (database, backups, `Rolling Stock photos`, config). It uses sts-docker's release stack (`docker-compose.release.yml`): the plugins are built into the image and only data folders are mounted. Both containers restart with the Pi.
2. The Pi's code changes only by a `git pull` of both repos and a rebuild (`tools/hosts/pi_sts_update.sh`). Nothing is copied into a running container on the Pi, and the sts-helpers do not run there.
3. Content is prepared and tested on the Mac, whose stacks stay: 8980 is the Mac's working copy and 8981 the sandbox. Prepared data reaches the Pi as an STS backup restored there. The Pi's database is the master of a session.
4. The Mac's `jmri_ops` setting points at the Mac's own JMRI (`host.docker.internal:12080`), so a Send Cars from the Mac never touches the layout's Operations roster. The Pi's points at `10.0.0.150:12080`, as in `jmri/layouts/hart/data/sts_jmri_ops_settings.json`.
5. `lnevo/sts-plugins` is public, so the Pi pulls both repos over HTTPS without a key.
6. The MT300 (10.0.0.60) lets `RPi-JMRI` clients reach 10.0.0.150 on TCP 8980, in its `Allow-JMRI-to-house` rule, with a `10.42.0.2:8980` forward like JMRI's.

## Consequences

- The Pi started from the session 5 checkpoint `hart_session_post5` (70 cars) plus the 10 CSX hoppers intook on 2026-11-08, placed empty on K-1 at Shenango Coke Works (`SHEN-COKE-SHIPPING`).
- `localhost:8980` is now the Mac copy, which is what the STS tools and tests reach by default. Live work sets `STS_API_URL=http://10.0.0.150:8980/sts/api/v1` for that job only; it is never a session-wide default, so a test or prep script cannot write to the live database by accident.
- Back up live sessions on the Pi; its backups folder is `~/sts/sts-docker-data/backups`. The Mac's backups folder no longer follows the live railroad.
- The Pi's userland is 32-bit (`armhf`) on a 64-bit kernel, so apt's Docker is 32-bit, and MariaDB publishes no 32-bit ARM image. The Pi runs Docker's static 64-bit binaries instead (`tools/hosts/pi_docker_static.sh`, which also updates them; `apt upgrade` does not). They need no 64-bit libraries, so the 32-bit system is untouched, and the official images run as arm64 with Docker's normal seccomp filter. Debian multiarch was rejected: its 64-bit `libc6` must match Raspberry Pi's `+rpt` build exactly.
- The Pi runs JMRI, Mosquitto, Apache/PHP and MariaDB. Watch its load during sessions; a rebuild loads it heavily for some minutes, so do not run one while the owner is operating.
