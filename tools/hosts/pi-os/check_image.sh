#!/usr/bin/env bash
# Check the newest built image read-only in the Lima build VM; exit 1 on any failure.
#
#   tools/hosts/pi-os/check_image.sh [image]     (build_image.sh runs it at the end)
#
# It cannot boot the image (there is no Pi 5 emulator); first boot, the desktop, the
# screens and the Wi-Fi are checked on the Pi (docs/hosts/PI_OS_REBUILD.md, Phase 5).
set -euo pipefail

PRIV="${HART_PI_OS_PRIVATE:-$HOME/.config/hart/pi-os}"
WORK="${HART_PI_OS_WORK:-$HOME/.cache/hart/pi-os}"
VM="${HART_PI_OS_VM:-hart-pi-build}"
img="${1:-$(ls -1t "$WORK"/out/*.img 2>/dev/null | head -1)}"
[[ -s "$img" ]] || { echo "no image in $WORK/out" >&2; exit 1; }

# Only a digest of the expected hash goes to the VM, never the hash.
# shellcheck disable=SC1091
want_sha="$(bash -c 'source "$1"; printf "%s" "$PI_PASSWORD_HASH"' _ "$PRIV/secrets.env" | shasum -a 256 | cut -c1-64)"

limactl shell --workdir / "$VM" sudo bash -s -- "$img" "$want_sha" <<'VM'
set -u
img="$1" want_sha="$2" fails=0 m=/mnt/hart-check
ok()  { echo "  ok   $*"; }
bad() { echo "  FAIL $*"; fails=$((fails + 1)); }
is()  { local what="$1" got="$2" want="$3"; [[ "$got" == "$want" ]] && ok "$what" || bad "$what: got '$got', want '$want'"; }

dev="$(losetup -fP --show -r "$img")"
mkdir -p "$m"
mount -o ro "${dev}p2" "$m" && mount -o ro "${dev}p1" "$m/boot/firmware" || { echo "cannot mount $img"; losetup -d "$dev"; exit 1; }
trap 'umount "$m/boot/firmware" "$m" 2>/dev/null; losetup -d "$dev"' EXIT
echo "checking $(basename "$img")"

is "architecture" "$(chroot "$m" dpkg --print-architecture)" arm64
grep -q 'VERSION_CODENAME=trixie' "$m/etc/os-release" && ok "trixie" || bad "not trixie"
is "/lib link" "$(readlink "$m/lib")" usr/lib
for f in edid.bin edid2.bin; do [[ -s "$m/usr/lib/firmware/edid/$f" ]] && ok "EDID $f" || bad "EDID $f missing"; done

for p in openjdk-21-jre cups cups-bsd mosquitto mosquitto-clients python3-paho-mqtt python3-serial \
         python3-flask git rsync tcpdump avahi-utils iw wpasupplicant samba wayvnc docker-ce; do
  st="$(chroot "$m" dpkg-query -W -f='${Status}' "$p" 2>/dev/null | awk '{print $3}')"
  [[ "$st" == installed ]] || bad "package $p: '${st:-absent}'"
done
ok "packages checked"

is "pi entry" "$(grep '^pi:' "$m/etc/passwd" | cut -d: -f3,4,6,7)" "1000:1000:/home/pi:/bin/bash"
have_sha="$(awk -F: '$1=="pi"{printf "%s", $2}' "$m/etc/shadow" | sha256sum | cut -c1-64)"
[[ "$have_sha" == "$want_sha" ]] && ok "pi password hash matches the old card" || bad "pi password hash differs from secrets.env"
is "/home/pi mode" "$(stat -c '%a %u' "$m/home/pi")" "700 1000"
is ".ssh mode" "$(stat -c '%a %u' "$m/home/pi/.ssh")" "700 1000"
is "authorized_keys mode" "$(stat -c '%a %u' "$m/home/pi/.ssh/authorized_keys")" "600 1000"
is "JMRI link" "$(readlink "$m/home/pi/JMRI")" JMRI.5.16
for d in JMRI.5.16 sts/sts-docker sts/sts-plugins lcos-bridge; do [[ -d "$m/home/pi/$d" ]] && ok "~/$d" || bad "~/$d missing"; done

left="$(find "$m/etc/sdm" "$m/home" "$m/root" "$m/tmp" -name pi.hash 2>/dev/null)"
[[ -z "$left" ]] && ok "no pi.hash left" || bad "pi.hash left: $left"

for c in Easte RPi-JMRI Ethernet; do
  f="$m/etc/NetworkManager/system-connections/$c.nmconnection"
  [[ -f "$f" ]] && ok "profile $c" || bad "profile $c missing"
done
for c in Easte RPi-JMRI; do
  grep -q '^psk=..*' "$m/etc/NetworkManager/system-connections/$c.nmconnection" 2>/dev/null \
    && ! grep -q '@.*_PSK@' "$m/etc/NetworkManager/system-connections/$c.nmconnection" && ok "$c password set" || bad "$c password not set"
done
grep -q '^autoconnect=false' "$m/etc/NetworkManager/system-connections/RPi-JMRI.nmconnection" && ok "hotspot does not autoconnect" || bad "hotspot autoconnects"

is "ssh host keys" "$(ls "$m"/etc/ssh/ssh_host_*_key 2>/dev/null | wc -l)" 3
[[ -s "$m/var/lib/samba/private/passdb.tdb" ]] && ok "Samba passwords" || bad "Samba passwords missing"
is "hostname" "$(cat "$m/etc/hostname")" RPi-JMRI
cl="$(cat "$m/boot/firmware/cmdline.txt")"
grep -qE '(^| )resize( |$)' <<< "$cl" && ok "cmdline has resize (first boot grows the root filesystem)" || bad "cmdline has no resize: the root filesystem stays at the image size"
[[ -L "$m/etc/systemd/system/sysinit.target.wants/rpi-resize.service" ]] && ok "rpi-resize.service enabled" || bad "rpi-resize.service not enabled: the filesystem would not grow"
grep -q 'drm.edid_firmware=HDMI-A-1:edid/edid.bin,HDMI-A-2:edid/edid2.bin' <<< "$cl" && ok "cmdline EDID" || bad "cmdline has no EDID setting"
is "cmdline video=" "$(grep -o 'video=[^ ]*' <<< "$cl" | tr '\n' ' ')" "video=HDMI-A-1:1920x1080@60D video=HDMI-A-2:1920x1080@60D "
[[ ! -e "$m/etc/initramfs-tools/conf.d/zz-hart-image-build" ]] && ok "build-only initramfs setting removed" || bad "zz-hart-image-build left in the image"
grep -qx vc4 "$m/etc/initramfs-tools/modules" && ok "vc4 listed for every initramfs" || bad "vc4 not in /etc/initramfs-tools/modules"
shopt -s nullglob
irds=("$m"/boot/firmware/initramfs*)
shopt -u nullglob
(( ${#irds[@]} )) || bad "no initramfs in /boot/firmware"
for ird in "${irds[@]}"; do
  n="$(basename "$ird")"
  if ! list="$(chroot "$m" lsinitramfs -l "/boot/firmware/$n")"; then bad "cannot list $n"; continue; fi
  is "EDID files in $n" "$(grep -cE 'usr/lib/firmware/edid/edid2?\.bin$' <<< "$list")" 2
  grep -qE ' lib -> usr/lib$' <<< "$list" && ok "$n has lib -> usr/lib (firmware loader path)" || bad "$n has no lib -> usr/lib link"
  grep -q '/vc4/vc4\.ko' <<< "$list" && ok "$n has vc4" || bad "$n has no vc4"
  grep -q 'scripts/local-premount/resize_early$' <<< "$list" && grep -q 'usr/s\?bin/parted$' <<< "$list" \
    && ok "$n has resize_early and parted" || bad "$n lacks resize_early or parted: the partition would not grow"
done

for b in lwrespawn wf-panel-pi kanshi lxsession-xdg-autostart; do [[ -x "$m/usr/bin/$b" ]] && ok "/usr/bin/$b" || bad "/usr/bin/$b missing (the display setup starts it)"; done
for k in "$m/home/pi/.config/kanshi/config" "$m/etc/xdg/labwc-greeter/config.kanshi"; do
  is "kanshi profiles in ${k#"$m"}" "$(grep -oE '^profile [a-z-]+' "$k" | tr '\n' ' ')" "profile both profile kvm-only profile direct-only "
done
is "panel 1 monitor" "$(grep '^monitor=' "$m/home/pi/.config/wf-panel-pi.ini")" "monitor=HDMI-A-1"
is "panel 2 monitor" "$(grep '^monitor=' "$m/home/pi/.config/wf-panel-pi-2.ini" 2>/dev/null)" "monitor=HDMI-A-2"
grep -q '^Exec=/usr/bin/lwrespawn /usr/bin/wf-panel-pi -c /home/pi/.config/wf-panel-pi-2.ini$' "$m/home/pi/.config/autostart/hart-panel-2.desktop" 2>/dev/null \
  && ok "second panel autostarts" || bad "second panel autostart missing"
grep -qx 'autologin-user=pi' "$m/etc/lightdm/lightdm.conf.d/hart-autologin.conf" 2>/dev/null \
  && ok "desktop logs pi in at boot" || bad "no desktop autologin: every boot asks for a login"

w="$m/etc/systemd/system/multi-user.target.wants"
# Enable links are absolute paths into the image, so test the link, not its target.
for s in wifi-watchdog mosquitto smbd nmbd docker ssh; do [[ -L "$w/$s.service" ]] && ok "$s enabled" || bad "$s not enabled"; done
[[ -L "$w/lcos-bridge.service" ]] && bad "lcos-bridge enabled" || ok "lcos-bridge off"
[[ -f "$m/etc/cloud/cloud-init.disabled" ]] && ok "cloud-init disabled" || bad "cloud-init not disabled"
[[ ! -e "$m/usr/local/lib/hart/display-setup.sh" ]] && ok "build-only display-setup.sh removed" || bad "display-setup.sh left in the image"
[[ -e "$m/etc/sdm/0piboot/060-runatboot.sh" ]] && ok "first-boot script queued" || bad "first-boot script missing"

echo "$fails failure(s)"
exit $(( fails > 0 ))
VM
