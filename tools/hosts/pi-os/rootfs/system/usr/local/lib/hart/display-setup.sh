#!/bin/bash
# Display fix 1 (docs/hosts/PI_OS_REBUILD.md, Displays), run once at image build (sdm post-install),
# which then deletes it: on the Pi it would rebuild the initramfs with the build-only MODULES=most.
#  - one video= per output, a mode vc4 accepts (no M: the CEA 1080p60 mode from the EDID,
#    not a computed CVT mode, which vc4 rejected) and D to keep each port on when the KVM
#    or the matrix reports nothing;
#  - list vc4 in /etc/initramfs-tools/modules, so every initramfs (this one, and the ones
#    kernel updates build with MODULES=dep) has vc4 and, through the hart-edid hook, the EDID;
#  - rebuild the initramfs.
set -euo pipefail
cmd=/boot/firmware/cmdline.txt
line="$(tr -d '\n' < "$cmd")"
line="$(sed -E 's/(^| )video=[^ ]+//g; s/^ +//; s/ +$//' <<< "$line")"
printf '%s video=HDMI-A-1:1920x1080@60D video=HDMI-A-2:1920x1080@60D\n' "$line" > "$cmd"
echo "cmdline: $(cat "$cmd")"
grep -qx vc4 /etc/initramfs-tools/modules || echo vc4 >> /etc/initramfs-tools/modules
# In sdm's container mkinitramfs cannot find the root device for MODULES=dep, so the
# build uses MODULES=most for this one run; kernel updates on the Pi go back to the default.
tmpconf=/etc/initramfs-tools/conf.d/zz-hart-image-build
trap 'rm -f "$tmpconf"' EXIT
echo MODULES=most > "$tmpconf"
update-initramfs -u -k all
