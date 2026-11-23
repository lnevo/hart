# Pi OS rebuild plan (2026-11-21, decisions 2026-11-23)

This is a plan for a new 64-bit Raspberry Pi OS (trixie) system on the layout Pi. It is built from scripts and config files kept in the repo, and the current card stays as the way back. The owner worked out the plan in a chat on 2026-11-21 and made the Phase 0 decisions on 2026-11-23. The build files are in [`tools/hosts/pi-os/`](../../tools/hosts/pi-os/README.md); a first image was built and checked on the Mac on 2026-11-23. On the Pi, only the display trial has changed anything: its settings stay live on the current card, with a revert script (Displays, Steps). It is a future goal in [`wiki/STATUS.md`](../../wiki/STATUS.md).

## What the Pi runs now

| | |
|---|---|
| Board | Raspberry Pi 5 Model B, 8 GB |
| OS | Raspbian 12 (bookworm), 32-bit userland (`armhf`) |
| Kernel | 6.12.115, 64-bit (updated 2026-11-17) |
| Image | Built from "Raspberry Pi reference 2023-12-05", the bookworm base of Steve Todd's RPi-JMRI image |
| Storage | 32 GB SD card, 40% used |
| Software | Java 17 (32-bit), Python 3.11, JMRI 5.16; Docker runs STS from static 64-bit binaries ([ADR-020](../../wiki/decisions/ADR-020-live-sts-on-the-pi.md)) |

Bookworm is one release behind. Raspberry Pi OS moved to Debian 13 (trixie) in October 2025, and bookworm is in Debian LTS. Because the userland is 32-bit, anything that ships only for 64-bit Linux needs workarounds or won't run at all: Docker, the ARMv7 build of arduino-cli, and Claude Code, which could not be installed on 2026-11-21.

## Why rebuild, and why from scratch

- Raspberry Pi doesn't support an in-place upgrade from bookworm to trixie, and that upgrade would keep the 32-bit userland anyway.
- Steve Todd's RPi-JMRI image still uses a bookworm base, and probably a 32-bit one. Its page couldn't be read directly (it returns 403 to automated fetches), and the newest image found was July 2026 with JMRI 5.16. A new copy of it would bring a newer JMRI but neither trixie nor 64-bit.
- So the new system starts from stock Raspberry Pi OS 64-bit (trixie). Steve's documented steps are followed, changed where trixie or HART differs.

## How the card differs from Steve's setup

- **Network:** the Pi isn't a hotspot. It joins the house Wi-Fi by DHCP and gets 10.0.0.150. The `RPi-JMRI` hotspot profile is still there but doesn't connect on its own.
- **PanelPro:** it starts with the fixed `TCS_MQTT` profile, launched by the deploy scripts (`pi_start_panelpro.sh`), not at login and not through AutoIdentify.
- **These exist only on this card, not in the repo:**
  - the Wi-Fi watchdog in `/usr/local/sbin`
  - the display setup (below)
  - an iptables rule that forwards port 12090 to 10.42.0.222
  - the Mosquitto config
- **Extra services:** the Mosquitto broker, Docker running STS, the speed-match publisher (`hart-speedmatch-live`), and the `lcos-bridge` service with its udev rule. The bridge service is installed but turned off.

## Build method: the image is made on the Mac

The image is built and loaded with software before any card is written, and the Pi keeps running meanwhile.

- **Where:** a Lima VM on the Mac (Debian 13, arm64, Apple virtualization), the same architecture as the Pi 5, so `apt` runs natively with no emulation. The first draft used a Docker container, but sdm's own docs say it does not work in Docker (it needs systemd-nspawn and loop devices); a full VM has both. The Windows box would need qemu emulation, which is slower.
- **Tool:** sdm (gitbls/sdm, pinned to V16.2). It customises a stock Raspberry Pi OS image: packages, users, Wi-Fi, locale, files and services, plus first-boot steps. Its config and our files are in `tools/hosts/pi-os/`, so a rebuild is one command (`build_image.sh`). The alternatives are Raspberry Pi's `rpi-image-gen` (more work to set up) or a plain loop-mount and chroot script.
- **Time:** about 5 minutes once the VM and the stock image are cached (13 minutes the first time, 2026-11-23), then Raspberry Pi Imager or `dd` writes the 13 GB image to the card. The root filesystem is about 12 GB in the image; `resize` in `cmdline.txt` (kept by sdm's `--expand-at-boot`) grows it to the whole card on first boot. Images built before 2026-11-23 18:34 lack it: add ` resize` to `cmdline.txt` on the card's boot partition before the first boot.
- **First build (2026-11-23):** the image checked out read-only in the VM: trixie arm64, all packages and Docker installed, `/lib` intact, the house Wi-Fi and hotspot profiles, the old ssh host keys and Samba passwords, hostname `RPi-JMRI`, and the planned services enabled. Stock trixie ships a locked placeholder `pi` (no password, `nologin`), so the build now gives it a shell and the old card's password hash; the rebuilt image has both. Not yet booted on a Pi.

### Baked into the image

- trixie 64-bit, fully upgraded: hostname `RPi-JMRI`, user `pi`, locale `en_US`, time zone `America/New_York`, IPv6 off
- Java 21, Samba, CUPS (decision 5), Mosquitto with its config, wayvnc, Docker from docker.com's trixie arm64 repo, and the Python packages
- the house Wi-Fi profile with power save off, and the hotspot profile (kept, never autoconnects), written as NetworkManager files
- JMRI 5.16 copied from the old card to `~/JMRI.5.16` (CATS is installed into it) with `~/JMRI` linked to it; the desktop icons and log link come from the first deploy; no PanelPro autostart (decision 3)
- the Wi-Fi watchdog, the display files and `cmdline.txt` settings, the udev rule, and the `lcos-bridge` checkout with its service off. No iptables rules: with the 12090 forward dropped (decision 4) nothing is left but Docker's own. The speed-match user service comes from the first deploy
- the old ssh host keys and `authorized_keys`, so the Mac and Windows don't see a changed host
- `~/sts` checked out (`sts-docker` on `active`, `sts-plugins` on `main`). The STS images are built on the Pi at swap time, after the database is restored, the way ADR-020 updates it anyway
- `JMRI_UserFiles` from the repo build (what `sync_hart_package.sh` ships)
- Claude Code (normal installer, 64-bit)

### Has to wait for the Pi

- **First boot, automatic:** `firstboot.sh` adds `pi` to the `docker` and `lpadmin` groups and turns on lingering for the speed-match service. The card is an SD card (decision 2), so the EEPROM boot order stays.
- **At swap time:** live data, copied from the old card at the last moment: the `~/.jmri` profile and preferences, the DecoderPro roster, the STS database (from a fresh `make sts-pull`), `mosquitto.db`, the speed-match ledger, `~/lcos-bridge/.bridgerc`, and any Store or Operations Pro changes through the usual pulls. The two HP printers are added again in CUPS.

### Testing before the card is written

There's no QEMU model of the Pi 5, so the image can't be booted on the Mac. What can be checked there: the image's userland in an arm64 container (Java starts JMRI headless, Mosquitto runs, the STS containers start), config linting, and a diff of the file list against the current card. PanelPro's screen, HDMI, Wi-Fi and the watchdog can only be tested on the Pi.

## Phase 0: owner decisions (done 2026-11-23)

1. Hotspot profile: **kept**, never connects on its own.
2. Storage: **a new SD card**. The old card is the rollback; NVMe can come later.
3. PanelPro: **started only by deploys** and `pi_start_panelpro.sh`, not at login.
4. The 12090 forward to 10.42.0.222: **dropped**, with the NAT rules that served it.
5. Printing (CUPS): **kept**. Two HP printers are set up on the old card.

Also decided: Claude Code goes on the Pi with the rebuild, not before (owner, 2026-11-21).

## Phase 1: copy everything off the current card

Done for the build inputs on 2026-11-23: the card-only files are in `tools/hosts/pi-os/`, and `pull_from_pi.sh` copied the secrets (Wi-Fi PSKs, the `pi` password hash, ssh host keys, `authorized_keys`, Samba passwords) to `~/.config/hart/pi-os` and the JMRI install to `~/.cache/hart/pi-os` on the Mac. The live data below is copied again at swap time.

With JMRI closed, after `make tables-pull-pi` and `make ops-pull`, and with nothing left unmerged:

- `~/.jmri`: the TCS_MQTT profile and preferences. Copy the profile, don't rebuild it.
- `~/JMRI_UserFiles`, mainly the DecoderPro roster. The deploy doesn't ship it, so the Pi's copy is the master.
- STS: a fresh `make sts-pull` backup and `~/sts/sts-docker-data`.
- `~/speedmatch` (ledger and rollback files) and the `lcos-bridge` checkout.
- The Mosquitto config and `/var/lib/mosquitto/mosquitto.db` (retained messages).
- The ssh host keys and `authorized_keys`.
- The watchdog script and unit, the EDID files, `config.txt`, `cmdline.txt`, the kanshi configs, the udev rule, the NetworkManager profiles and the iptables rules.

Most of this goes into the repo under `tools/hosts/pi-os/`. Secrets don't: Wi-Fi passwords and keys stay in a private backup.

## Phase 2: Steve's steps, adapted

| Steve's step | New build |
|---|---|
| Bookworm desktop image | Raspberry Pi OS 64-bit trixie desktop; hostname, user, ssh key, Wi-Fi, locale and time zone set by the image build (this replaces his Raspberry Pi Configuration step) |
| `apt full-upgrade` | Same |
| `openjdk-17-jre samba cups-bsd labwc` | trixie probably no longer ships Java 17, so `openjdk-21-jre`; check that JMRI 5.16 runs on it. labwc is already the default. Add `mosquitto mosquitto-clients python3-paho-mqtt python3-serial python3-flask git rsync`, plus Docker from docker.com |
| Hotspot 192.168.6.1/24 | Only if kept (decision 1). The main link is the house Wi-Fi client connection |
| Wired DHCP, IPv6 off | Same, on both connections |
| `RPi-JMRI.local` | avahi does this by default |
| Samba share | Two shares, as now: `JMRI_UserFiles` and `JMRI_Settings` (`~/.jmri`), plus `smbpasswd -a pi` |
| `vncpasswd -service` (RealVNC) | wayvnc, the trixie default |
| raspi-config → Wayland → labwc | Not needed, already the default |
| Wi-Fi power save off | `nmcli c modify <house Wi-Fi> 802-11-wireless.powersave 2`, and the hotspot too if kept |
| JMRI to `~/JMRI` | `~/JMRI.5.16` with `~/JMRI` linked to it, as the deploy scripts expect |
| Hardware profiles, WiThrottle and web server autostart | Restore the copied `TCS_MQTT` profile (WiThrottle 12090 and web 12080 already set). Skip his set of hardware profiles |
| Log symlink | Same: `~/JMRI_UserFiles/log` → `~/.jmri/log` |
| Desktop icons, File Manager setting | `tools/hosts/pi/install_desktop_icons.sh` (CATS ABS and CTC, TrainStat), his log and user-files icons, and the File Manager option |
| PanelPro autostart | Per decision 3. AutoIdentify isn't needed with one fixed profile |
| `usermod -aG lpadmin` | Per decision 5. Also add `dialout`, `docker` and `gpio` |
| Cleanup and Win32DiskImager image | Not needed, since nothing is published. Keep the old card as the rollback; once the new card is accepted, take a private image of it as a golden copy (it holds keys and Wi-Fi passwords, so it is never published) |

## Phase 3: HART additions

1. **Mosquitto:** listener on 1883, anonymous access and persistence as now, and `mosquitto.db` restored.
2. **Docker and STS:** `sts-docker` and `sts-plugins` cloned into `~/sts`, started with `docker-compose.yml` plus `docker-compose.release.yml`, database restored from the Phase 1 backup. Per ADR-020 the Pi gets STS only by git pull and rebuild.
3. **System files:** the Wi-Fi watchdog (script and unit), the display setup, and the iptables rules (without the 12090 forward if it's dropped).
4. **Services:** `hart-speedmatch-live` (already in the repo), and `lcos-bridge` with its udev rule and service, left off unless the bridge has moved to the Pi by then.
5. **Deploy:** `sync_hart_package.sh --pi --win` puts `JMRI_UserFiles` back from the repo; the roster is copied over the result.

## Displays

Status: done (2026-11-23). The owner closed the display topic: the fix is live on the current card and in the image. What only the new card can show (the trixie Control Centre and kanshi, the kernel the Pi 5 boots) is checked in Phase 5, item 9.

Each Pi HDMI port goes into an SFX HDMI Matrix: HDMI-A-2 directly, HDMI-A-1 through a KVM shared with the Windows box (found by the KVM flip test, 2026-11-23). The matrix feeds the local monitor and the crew lounge screen, so the lounge can show the Pi while the local monitor is on Windows. Both outputs are needed. Nothing is set on the matrix or the monitors themselves.

### Setup on the card (made 2026-02-21)

- **Stored EDID:** the matrix's EDID was copied from `/sys/class/drm/card1-HDMI-A-{1,2}/edid` to `/lib/firmware/edid/edid.bin` and `edid2.bin`. The two files are identical, 256 bytes each.
- **Kernel command line** (`/boot/firmware/cmdline.txt`):
  ```
  drm.edid_firmware=HDMI-A-1:edid/edid.bin,HDMI-A-2:edid/edid2.bin
  video=HDMI-A-1:1920x1080M@60,HDMI-A-2:1920x1080M@60
  ```
  `config.txt` also has `hdmi_edid_file=1`, an old firmware setting that the KMS driver probably ignores.
  This `video=` setting forces nothing: vc4 rejects it, logging `User-defined mode not supported: "1920x1080": 60 148500 …` (the `M` makes it a CVT mode at 148.5 MHz). The two outputs also share one `video=` with a comma, where the kernel expects one per output.
- **Mirroring through kanshi:** both outputs at 1920×1080@60, position 0,0, in `~/.config/kanshi/config` (desktop) and `/etc/xdg/labwc-greeter/config.kanshi` (login screen).

### What is wrong with it

- **The stored EDID has never loaded.** Every boot logs `Requesting EDID firmware "edid/edid.bin" failed (err=-2)` for both ports. The initramfs (`auto_initramfs=1`) holds the graphics driver `vc4.ko` but not the EDID files, and the driver starts before the root filesystem is mounted. It falls back to whatever the matrix reports at that moment.
- **The outputs seem to swap.** HDMI-A-1 and HDMI-A-2 are fixed to the physical sockets, so the names don't actually swap. The likely cause is the KVM at boot: if the Pi boots while the KVM is on Windows, HDMI-A-1 may be missing, and the boot starts with one output (not tested yet). With the Pi running, a flip does no harm: in the KVM flip test HDMI-A-1 went disconnected, lost its EDID and came back with the same EDID within about 0.5 s, and HDMI-A-2 never changed. Then the kanshi profile, which needs both outputs, doesn't match, and labwc lays the outputs side by side. The matrix reports identical monitors on both ports, so make-and-model matching can't tell them apart. A `desktop-items-NOOP-1.conf` shows the Pi has booted at least once with no screen detected.
- **The menu bar shows on one monitor.** labwc has no real mirror mode; outputs at 0,0 overlap, but the panel is drawn per output, and `wf-panel-pi` is pinned to `monitor=HDMI-A-1`, the port behind the KVM.

### Fixes

1. **Keep both outputs present** whatever the KVM or matrix does: an initramfs hook so the stored EDID loads, and the `D` suffix on `video=` to force each port on, one `video=` per output. The mode must be one vc4 accepts: `1920x1080M@60` is rejected, so the trial tries `video=HDMI-A-1:1920x1080@60D` (no `M`) and checks the kernel log.
2. **Menu bar on both monitors:** a second `wf-panel-pi` started from the labwc autostart with its own `-c` config and `monitor=HDMI-A-2`. If the panel refuses to run twice, pin the one panel to HDMI-A-2, the port that goes straight to the matrix, so the crew lounge always has it.
3. **Fallback kanshi profiles** for the one-output and no-output cases, so an odd boot still gets 1920×1080 at 0,0.
4. **VNC** shows one output; with the overlap reliable, both show the same picture.

On trixie, check whether vc4 still loads from the initramfs, and that the new Control Centre still uses kanshi and these paths and doesn't overwrite the mirror profile.

### Steps (done 2026-11-23)

1. **KVM flip test:** done 2026-11-23, read-only over ssh with the owner flipping the KVM. HDMI-A-1 is the KVM port and blinks for about 0.5 s on a flip; HDMI-A-2 is direct and never changed; both report the matrix's identical 256-byte EDID (md5 prefix `2402b21d`); vc4 rejects the `video=` mode.
2. **Trial on the current card:** passed 2026-11-23 (session hart-6d, the owner checked it at the screens). Round 1: fixes 2 and 3; `wf-panel-pi` runs twice without trouble, the second copy from `~/.config/autostart/hart-panel-2.desktop` with `~/.config/wf-panel-pi-2.ini` (`monitor=HDMI-A-2`), and kanshi has the profiles `both`, `kvm-only` and `direct-only` in the desktop and login-screen configs. Round 2: fix 1, the repo's `hart-edid` hook and `video=HDMI-A-1:1920x1080@60D video=HDMI-A-2:1920x1080@60D`; three boots each logged `[drm] forcing HDMI-A-n connector on` for both ports, no `EDID firmware … failed` and no `User-defined mode not supported`, and `wlr-randr` showed both ports at 1920x1080@60, 0,0. Mirroring and a menu bar on both screens held through KVM flips and reboots. Not measured: whether HDMI-A-1's status still blinks on a flip with `D` (the owner says it no longer matters). The trial stays on the current card; `~/display-trial-revert.sh` (with sudo, then reboot) restores the backups in `/boot/firmware/*.pre-trial` and `~/display-trial-backup/`.
3. **Into the image:** done 2026-11-23. Fix 1: `display-setup.sh` writes the two `video=` entries and rebuilds the initramfs, and the `hart-edid` hook puts both EDID files in it, with `vc4` listed in `/etc/initramfs-tools/modules` so initramfs files rebuilt by kernel updates keep both. The build makes its one initramfs with `MODULES=most`, because `mkinitramfs` cannot find the root device inside sdm's container; the Pi's own rebuilds use the default. Fixes 2 and 3: the trial's files, copied from the Pi unchanged except their comments. `check_image.sh` checks all of it. If the new card shows no picture, take `D` off the two `video=` entries in `cmdline.txt` from the Mac.

## Phase 4: swap, with a way back

There is one Pi 5, so this needs a maintenance window. Turn the operating flag on, pull, shut down, put in the new card or drive, boot, restore the live data and deploy. If anything fails, put the old card back; it isn't touched at any point.

## Phase 5: acceptance checks

1. `uname -m` and `dpkg --print-architecture` report `aarch64` and `arm64`.
2. ssh from the Mac and Windows works with no host-key warning.
3. Mosquitto answers on 10.0.0.150:1883 and the retained topics are back.
4. PanelPro starts with TCS_MQTT; the web server (12080) and WiThrottle (12090) respond.
5. CATS ABS and CTC open from their icons.
6. STS on port 8980 shows the restored data.
7. `make deploy-status` matches and `make panelpro-test` passes on the Mac.
8. VNC and both Samba shares work.
9. The watchdog runs, and after a cold boot both outputs show 1920×1080 mirrored on the login screen and the desktop, also when the matrix or KVM comes up late.
10. A short operating session runs with the LCOS bridge.
11. `claude --version` works.

## Phase 6: write it down

An ADR for the OS base (64-bit trixie built from the repo, not the RPi-JMRI image), `wiki/STATUS.md` updated, and the old card kept for about a month before reuse.
