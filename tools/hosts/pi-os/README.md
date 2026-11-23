# Layout Pi OS image

This folder (kept outside `tools/hosts/pi/`, which every deploy ships to the hosts) holds the build for the layout Pi's new 64-bit Raspberry Pi OS (trixie) card: an sdm pluglist, the files that only lived on the old card, and the scripts that build the image on the Mac. The plan, decisions and swap steps are in [`docs/hosts/PI_OS_REBUILD.md`](../../../docs/hosts/PI_OS_REBUILD.md).

## Build

```sh
tools/hosts/pi-os/pull_from_pi.sh     # read-only on the Pi: secrets and the JMRI install
tools/hosts/pi-os/build_image.sh      # Lima VM on the Mac; about 30 to 60 minutes
tools/hosts/pi-os/build_image.sh --stop
```

The image lands in `~/.cache/hart/pi-os/out/` with a `.sha256` and a `.base` file naming the stock image it came from. Write it to the new SD card with Raspberry Pi Imager ("Use custom", no OS customisation) or `dd`. It holds the Wi-Fi passwords and ssh host keys, so it never leaves the Mac.

## What is where

| Path | What |
|---|---|
| `hart.pluglist.in` | sdm plugins: user, locale, network, packages, Docker, Samba, wayvnc, files, services, kernel command line |
| `apps.txt` | apt packages added to the stock desktop image |
| `network/` | NetworkManager profiles; the two Wi-Fi ones are templates filled from `secrets.env` |
| `rootfs/system/` | copied to `/` as root: Wi-Fi watchdog, `lcos-bridge` unit, udev rule, Mosquitto config, EDID files (in `usr/lib`, as trixie merges `/lib` into `/usr`), greeter kanshi profile |
| `rootfs/home-pi/` | copied to `/home/pi`: kanshi, labwc environment, panel settings, aliases |
| `samba-shares.conf` | the `JMRI_UserFiles` and `JMRI_Settings` shares |
| `firstboot.sh` | run once on the Pi: `docker` and `lpadmin` groups, lingering for user services |
| `pull_from_pi.sh` | copies secrets to `~/.config/hart/pi-os` (mode 700) and JMRI to `~/.cache/hart/pi-os` |
| `build_image.sh`, `inside_vm.sh` | the build: stage, Lima VM, sdm customize, sdm burnfile with the hostname `RPi-JMRI` |

Secrets never enter the repo. `secrets.env` holds `HOUSE_WIFI_PSK`, `HOTSPOT_PSK` and `PI_PASSWORD_HASH`; the build copies them into a stage folder and deletes them from it when it ends.

## Not in the image

The swap brings these from the old card: the `~/.jmri` profile, the DecoderPro roster, the STS database, `mosquitto.db`, the speed-match ledger and `~/lcos-bridge/.bridgerc`. The first `sync_hart_package.sh --pi --win` deploy installs `JMRI_UserFiles`, the desktop icons and the speed-match service. STS is built on the Pi after its database is restored.

The display files are today's settings, unchanged. The fixes in the plan go in after the trial on the old card.
