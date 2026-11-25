# ADR-035 — What is backed up, where and how often

- **Status:** Accepted
- **Date:** 2026-11-25
- **Deciders:** lnevo

## Context

A read-only review on 2026-11-25 found the repo safe on GitHub, the Mac in Time Machine (one local disk) and nothing else on a schedule. The Pi had no backup job: its PanelPro profile (`~/.jmri`), the DecoderPro roster (deploys do not ship it) and `~/speedmatch` existed only on its SD card and on the old card kept until 2026-12-23. The newest copy of the live STS database on the Mac was 7 days old; it had not changed since. The Mac's gitignored data (`media/`, `ops/car-cards/`, `docs/wiring/bench/`) and the AnyRail plans had second copies only in Time Machine and in 11 to 15 day old copies on the Windows box.

## Decision

1. **Pi to Mac, daily.** A LaunchAgent on the Mac (`com.hart.backup-pi`, 03:30) runs `tools/hosts/backup_pi_pull.sh`: `~/.jmri`, the JMRI user files and `~/speedmatch`, plus the small extras restored at the 2026-11-23 swap (`~/Desktop`, `~/.java`, the app launchers, `~/jmrihelp`; a failure there warns but keeps the snapshot), as a dated snapshot in `~/Backups/hart/pi/` (unchanged files are hard links to the day before; 30 kept), then `pi_sts_pull_backups.sh` (the STS web-app backups and a database dump, 30 kept). It only reads on the Pi.
2. **Mac to Windows, weekly.** A LaunchAgent (`com.hart.backup-win`, Sundays 04:30) runs `tools/hosts/backup_win_push.sh`, mirroring `media/`, `ops/car-cards/`, `docs/wiring/bench/`, the STS copies from the Pi, the Pi snapshots, `~/Documents/Layout` and `~/Documents/NMRA AP` into `~/backups/mac/` inside WSL on the Windows box, keeping the snapshots' hard links. A file changed or deleted on the Mac is moved to `replaced/<time>/` there and kept 90 days.
3. **Time Machine** stays the Mac's own backup, and so covers everything in 1 and 2 that lands on the Mac.
4. **No card image** of the Pi (owner): a new card is built from `tools/hosts/pi-os/` (ADR-032), and the live data comes back from the snapshots in 1.
5. **No off-site copy for now** (owner): the Windows box is a second machine in the same house. Secrets (`~/.config/hart/pi-os`, `~/.ssh`, `.env.local`, the router notes) are only on the Mac and in Time Machine; they are not copied to Windows.
6. `make backup-status` prints when each job last ran in full and says OVERDUE after 2 days (Pi) or 9 days (Windows). `tools/hosts/backup_launchagents.sh install` sets both jobs up again on a new Mac.

## Consequences

- Before calling data safe, check it is in this list and that `make backup-status` is current. Data not listed here (the website's Hestia homes and mail, the Windows JMRI profile preferences, `mosquitto.db`) has no copy beyond its own host or Lightsail's snapshots.
- A Pi rebuild restores `~/.jmri`, the roster and `~/speedmatch` from the newest snapshot, and the STS from the newest dump (load it into the sandbox first to look, never straight into the Pi); see [`docs/hosts/PI_OS_REBUILD.md`](../../docs/hosts/PI_OS_REBUILD.md).
- A Mac that is asleep at the scheduled time runs the job when it wakes; a Mac away from home misses the Pi and Windows until it is back, and `backup-status` shows it.
- The Windows copy lives inside the WSL disk image; resetting that WSL distribution deletes it.
