#!/usr/bin/env bash
# Build the layout Pi's Raspberry Pi OS image on the Mac (docs/hosts/PI_OS_REBUILD.md).
#
#   tools/hosts/pi-os/pull_from_pi.sh      # once, and again after secrets or JMRI change
#   tools/hosts/pi-os/build_image.sh       # about 13 minutes the first time, 5 once cached
#   tools/hosts/pi-os/check_image.sh       # checks the newest image read-only in the VM
#   tools/hosts/pi-os/build_image.sh --stop   # stop the build VM afterwards
#
# sdm does not run in Docker, so the build runs in a Lima VM (Debian 13, arm64,
# Apple virtualization), the same architecture as the Pi 5: no emulation.
# Output: $HART_PI_OS_WORK/out/hart-pi-os-<date>.img and its .sha256. The image holds
# the Wi-Fi passwords and ssh host keys, so it never leaves the Mac or goes in the repo.
# Nothing here touches the running Pi.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PRIV="${HART_PI_OS_PRIVATE:-$HOME/.config/hart/pi-os}"
WORK="${HART_PI_OS_WORK:-$HOME/.cache/hart/pi-os}"
VM="${HART_PI_OS_VM:-hart-pi-build}"
STAGE="$WORK/stage"

ts() { date +%H:%M; }
log() { echo "[$(ts)] $*"; }

if [[ "${1:-}" == "--stop" ]]; then
  limactl stop "$VM"
  exit 0
fi

command -v limactl >/dev/null || { echo "limactl not found (MacPorts or Homebrew: lima)" >&2; exit 1; }
for f in secrets.env authorized_keys passdb.tdb ssh-host-keys/ssh_host_ed25519_key; do
  [[ -s "$PRIV/$f" ]] || { echo "missing $PRIV/$f: run pull_from_pi.sh first" >&2; exit 1; }
done
[[ -d "$WORK/jmri/JMRI.5.16" ]] || { echo "missing $WORK/jmri/JMRI.5.16: run pull_from_pi.sh first" >&2; exit 1; }

# Stage: this folder, the secrets, the rendered network profiles and the checkouts.
# The stage is the only folder the VM sees. Secrets are removed from it when the build ends.
log "staging into $STAGE"
mkdir -p "$STAGE" "$WORK/out" "$WORK/cache"
trap 'rm -rf "$STAGE/private" "$STAGE/net"' EXIT
rsync -a --delete "$HERE/" "$STAGE/os/"
umask 077
rsync -a --delete "$PRIV/" "$STAGE/private/"
mkdir -p "$STAGE/net"
# shellcheck disable=SC1091
source "$PRIV/secrets.env"
# Unquoted replacements are literal in bash 3.2 (macOS) and, with this off, in 5.2.
shopt -u patsub_replacement 2>/dev/null || true
render() { # template -> file, filling @KEY@ from secrets.env; values are taken literally
  local t; t="$(<"$1")"
  t="${t//@HOUSE_WIFI_PSK@/$HOUSE_WIFI_PSK}"
  t="${t//@HOTSPOT_PSK@/$HOTSPOT_PSK}"
  printf '%s\n' "$t" > "$2"
}
render "$HERE/network/Easte.nmconnection.in" "$STAGE/net/Easte.nmconnection"
render "$HERE/network/RPi-JMRI.nmconnection.in" "$STAGE/net/RPi-JMRI.nmconnection"
[[ "${PI_PASSWORD_HASH:-}" == \$* ]] || { echo "PI_PASSWORD_HASH in secrets.env is not a crypt hash: run pull_from_pi.sh" >&2; exit 1; }
printf '%s\n' "$PI_PASSWORD_HASH" > "$STAGE/private/pi.hash"
umask 022

# Checkouts and JMRI go to /home/pi as they are in home/.
mkdir -p "$STAGE/home/sts"
clone() { # url branch dest
  if [[ -d "$3/.git" ]]; then git -C "$3" fetch -q origin "$2" && git -C "$3" checkout -q -B "$2" "origin/$2"
  else git clone -q --branch "$2" "$1" "$3"; fi
  log "  $(basename "$3") at $(git -C "$3" rev-parse --short HEAD)"
}
clone https://github.com/lnevo/sts-docker.git active "$STAGE/home/sts/sts-docker"
clone https://github.com/lnevo/sts-plugins.git main "$STAGE/home/sts/sts-plugins"
clone https://github.com/lnevo/LCOS_ESP32_MQTT_Client.git main "$STAGE/home/lcos-bridge"
rsync -a --delete "$WORK/jmri/JMRI.5.16/" "$STAGE/home/JMRI.5.16/"

# The VM: created once, mounts only $WORK (writable).
if ! limactl list -q 2>/dev/null | grep -x "$VM" >/dev/null; then
  log "creating Lima VM $VM (Debian 13 arm64)"
  limactl create --tty=false --name="$VM" --vm-type=vz --arch=aarch64 \
    --cpus=4 --memory=6 --disk=40 --mount-only="$WORK:w" template:debian-13
fi
limactl list --format '{{.Status}}' "$VM" 2>/dev/null | grep -q Running || { log "starting $VM"; limactl start --tty=false "$VM"; }

log "building in $VM (sdm customize, then burnfile with the hostname)"
limactl shell --workdir / "$VM" sudo bash "$STAGE/os/inside_vm.sh" "$STAGE" "$WORK"
log "done: $(ls -1t "$WORK"/out/*.img | head -1)"
log "checking the image"
"$HERE/check_image.sh"
