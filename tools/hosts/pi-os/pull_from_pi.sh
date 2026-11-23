#!/usr/bin/env bash
# Copy what the new Pi image needs from the running Pi, read-only on the Pi.
#
#   tools/hosts/pi-os/pull_from_pi.sh
#
# Writes two places, both outside the repo:
#   $HART_PI_OS_PRIVATE (default ~/.config/hart/pi-os, mode 700): secrets
#     secrets.env        Wi-Fi PSKs and the pi password hash
#     ssh-host-keys/     /etc/ssh/ssh_host_*  (Mac and Windows keep trusting the Pi)
#     authorized_keys    ~pi/.ssh/authorized_keys
#     passdb.tdb         Samba passwords
#   $HART_PI_OS_WORK (default ~/.cache/hart/pi-os): bulky but not secret
#     jmri/JMRI.5.16/    the JMRI install as it runs now (CATS is installed into it)
#
# Nothing secret is printed. Live data (profile, roster, STS database, mosquitto.db)
# is not copied here: it is taken at swap time (docs/hosts/PI_OS_REBUILD.md, Phase 4).
set -euo pipefail

HOST="${PI_HOST:-${HART_PI_SSH:-pi}}"
PRIV="${HART_PI_OS_PRIVATE:-$HOME/.config/hart/pi-os}"
WORK="${HART_PI_OS_WORK:-$HOME/.cache/hart/pi-os}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST")

umask 077
mkdir -p "$PRIV/ssh-host-keys" "$WORK/jmri"
chmod 700 "$PRIV"

echo "[pull] secrets -> $PRIV"
"${SSH[@]}" 'sudo -n tar cf - -C / etc/ssh/ssh_host_ecdsa_key etc/ssh/ssh_host_ecdsa_key.pub \
    etc/ssh/ssh_host_ed25519_key etc/ssh/ssh_host_ed25519_key.pub \
    etc/ssh/ssh_host_rsa_key etc/ssh/ssh_host_rsa_key.pub' \
  | tar xf - -C "$PRIV/ssh-host-keys" --strip-components 2
"${SSH[@]}" 'cat ~/.ssh/authorized_keys' > "$PRIV/authorized_keys"
"${SSH[@]}" 'sudo -n cat /var/lib/samba/private/passdb.tdb' > "$PRIV/passdb.tdb"

# secrets.env: one KEY=value per line (printf %q quoting), read by build_image.sh.
"${SSH[@]}" 'sudo -n sh -c '\''
  psk() { sed -n "s/^psk=//p" "/etc/NetworkManager/system-connections/$1.nmconnection"; }
  printf "HOUSE_WIFI_PSK=%s\n" "$(psk Easte)"
  printf "HOTSPOT_PSK=%s\n" "$(psk RPi-JMRI)"
  printf "PI_PASSWORD_HASH=%s\n" "$(getent shadow pi | cut -d: -f2)"
'\''' > "$PRIV/secrets.env.tmp"
# Re-quote each value with printf %q so any character survives sourcing.
: > "$PRIV/secrets.env"
while IFS='=' read -r k v; do
  [[ -n "$v" ]] || { echo "[pull] $k is empty" >&2; exit 1; }
  printf '%s=%q\n' "$k" "$v" >> "$PRIV/secrets.env"
done < "$PRIV/secrets.env.tmp"
rm -f "$PRIV/secrets.env.tmp"
echo "[pull] secrets.env has $(wc -l < "$PRIV/secrets.env" | tr -d ' ') values; $(ls "$PRIV/ssh-host-keys" | wc -l | tr -d ' ') host key files"

echo "[pull] JMRI install -> $WORK/jmri"
umask 022
rsync -a --delete -e "ssh -o BatchMode=yes" "$HOST:JMRI.5.16/" "$WORK/jmri/JMRI.5.16/"
du -sh "$WORK/jmri/JMRI.5.16" | sed 's/^/[pull] /'
