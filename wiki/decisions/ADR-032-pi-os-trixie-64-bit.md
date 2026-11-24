# ADR-032 — The layout Pi runs 64-bit trixie, built from the repo

- **Status:** Accepted
- **Date:** 2026-11-23
- **Deciders:** lnevo

## Context

The Pi 5 ran Steve Todd's RPi-JMRI image on a bookworm base with a 32-bit userland. Docker, arduino-cli and Claude Code need 64-bit, bookworm is one release behind, and Raspberry Pi has no in-place upgrade to trixie. The card's own setup (watchdog, display, Mosquitto, network) lived only on the card.

## Decision

1. The Pi runs stock Raspberry Pi OS 64-bit (trixie), customised by sdm from `tools/hosts/pi-os/`; the RPi-JMRI image is no longer the base. Steve's steps are followed where they still apply.
2. The image is built on the Mac in a Lima VM (Debian 13 arm64), since sdm does not run in Docker, and checked read-only by `check_image.sh` before a card is written.
3. Secrets (Wi-Fi passwords, the `pi` password hash, ssh host keys, Samba passwords) stay out of the repo, in `~/.config/hart/pi-os` on the Mac; the image keeps the old host keys, so the Mac and Windows trust the new card.
4. Owner decisions (2026-11-23): keep the hotspot profile, off; a new SD card; PanelPro starts only from deploys; drop the 12090 forward; keep CUPS.
5. Docker comes from Docker's apt repository and updates with `apt upgrade`; the static binaries of ADR-020 are retired with the 32-bit userland.
6. The display setup proven in the 2026-11-23 trial is part of the image.

## Consequences

- A rebuild is `pull_from_pi.sh` and `build_image.sh`, about 5 minutes once cached. Live data (profile, roster, STS database, `mosquitto.db`) still moves at swap time.
- Data files laid out in memory pages need care when moving from the old 4 KB-page kernel to the Pi 5's 16 KB pages: MariaDB's `tc.log` had to be set aside.
- JMRI's known MQTT startup race (STATUS, "MQTT startup race") showed on the new card's first PanelPro start, after none in the old card's last 13: it drops and restores the broker connection within about 15 seconds. JMRI stays stock.
- The swap, the checks and what is open are in [`docs/hosts/PI_OS_REBUILD.md`](../../docs/hosts/PI_OS_REBUILD.md).
