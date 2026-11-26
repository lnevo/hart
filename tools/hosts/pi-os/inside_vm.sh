#!/usr/bin/env bash
# Runs as root inside the Lima build VM; called by build_image.sh. Not for the Pi.
#   inside_vm.sh <stage dir> <work dir>
set -euo pipefail

STAGE="$1"
WORK="$2"
SDM_RELEASE="${SDM_RELEASE:-V16.2}"
# The newest 64-bit desktop image; the resolved file name is printed and kept.
IMG_URL="${PI_OS_IMAGE_URL:-https://downloads.raspberrypi.com/raspios_arm64_latest}"
HOSTNAME_PI="RPi-JMRI"
TMP=/var/tmp/hart-pi-os   # the VM's own disk: loop devices on the shared mount are slow
OUT="$WORK/out"

ts() { date +%H:%M; }
log() { echo "[$(ts) vm] $*"; }

# 1. sdm, pinned to a release.
if [[ ! -x /usr/local/sdm/sdm ]] || ! grep -q "$SDM_RELEASE" /usr/local/sdm/sdm-version 2>/dev/null; then
  log "installing sdm $SDM_RELEASE"
  apt-get -qq update
  apt-get -qq install -y curl xz-utils >/dev/null
  curl -fsSL "https://raw.githubusercontent.com/gitbls/sdm/$SDM_RELEASE/install-sdm" -o /tmp/install-sdm
  bash /tmp/install-sdm "$SDM_RELEASE" >/dev/null
  echo "$SDM_RELEASE" > /usr/local/sdm/sdm-version
fi

# 2. The stock image, checked against Raspberry Pi's published SHA-256.
mkdir -p "$TMP" "$WORK/cache" "$OUT"
real_url="$(curl -fsSLI -o /dev/null -w '%{url_effective}' "$IMG_URL")"
name="$(basename "$real_url")"
if [[ ! -s "$WORK/cache/$name" ]]; then
  log "downloading $name"
  curl -fSL --progress-bar "$real_url" -o "$WORK/cache/$name.part"
  mv "$WORK/cache/$name.part" "$WORK/cache/$name"
fi
want="$(curl -fsSL "$real_url.sha256" | awk '{print $1}')"
have="$(sha256sum "$WORK/cache/$name" | awk '{print $1}')"
[[ "$want" == "$have" ]] || { echo "SHA-256 mismatch for $name" >&2; exit 1; }
log "base image $name (sha256 ok)"

base="$TMP/base.img"
# A failed sdm run can leave its loop device attached; detach it before reusing the file.
losetup -j "$base" 2>/dev/null | cut -d: -f1 | xargs -r -n1 losetup -d
udevadm settle 2>/dev/null || true
xz -dc "$WORK/cache/$name" > "$base"

# 3. The pluglist, filled in.
# Literal replacements: bash 5.2 would otherwise treat & as the match.
shopt -u patsub_replacement 2>/dev/null || true
umask 077
trap 'rm -f "$TMP/hart.pluglist"' EXIT
t="$(<"$STAGE/os/hart.pluglist.in")"
t="${t//@STAGE@/$STAGE}"
printf '%s\n' "$t" > "$TMP/hart.pluglist"
umask 022

# 4. Customize (Phase 0, Phase 1 and post-install run natively: arm64 VM, arm64 image).
log "sdm --customize"
/usr/local/sdm/sdm --customize --batch --extend --xmb 6144 \
  --plugin "@$TMP/hart.pluglist" --restart "$base"

# 5. Write a card image with the hostname (sdm sets the hostname at burn time).
stamp="$(date +%Y%m%d-%H%M)"
final="$TMP/hart-pi-os-$stamp.img"
log "sdm --burnfile (hostname $HOSTNAME_PI)"
# --expand-at-boot keeps `resize` in cmdline.txt, so the first boot grows the root filesystem
# to the whole card; without it sdm removes `resize`, expecting to expand during a --burn.
/usr/local/sdm/sdm --burnfile "$final" --hostname "$HOSTNAME_PI" --expand-at-boot "$base"

mv "$final" "$OUT/"
(cd "$OUT" && sha256sum "$(basename "$final")" > "$(basename "$final").sha256")
echo "$name" > "$OUT/hart-pi-os-$stamp.base"
rm -f "$base" "$TMP/hart.pluglist"
log "image $OUT/hart-pi-os-$stamp.img ($(du -h "$OUT/hart-pi-os-$stamp.img" | cut -f1)) from $name"
