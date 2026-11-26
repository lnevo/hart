#!/bin/bash
# First boot of the new layout Pi card, run once by sdm (runatboot) as root.
# Output: /var/log/hart-firstboot.log. Safe to run again by hand.
set -u
echo "hart-firstboot $(date -Is)"

# Groups that exist only after Docker and CUPS are installed.
for g in docker lpadmin; do
  if getent group "$g" >/dev/null; then usermod -aG "$g" pi; else echo "WARNING: no group $g"; fi
done
echo "pi groups: $(id -nG pi)"


# The pi user's services (speed-match publisher) run without a login, as on the old card.
loginctl enable-linger pi && echo "linger on for pi"

# The bridge is installed but stays off until it moves to the Pi.
systemctl disable --now lcos-bridge.service 2>/dev/null || true

# Claude Code for pi (owner, 2026-11-21), from its normal installer. It needs the network,
# which may still be coming up this early in the first boot.
nm-online -s -t 120 >/dev/null 2>&1 || echo "WARNING: no network after 120 s"
if sudo -u pi -H bash -o pipefail -c 'curl -fsSL https://claude.ai/install.sh | bash' >/dev/null; then
  echo "claude: $(sudo -u pi -H /home/pi/.local/bin/claude --version 2>&1 | head -1)"
else
  echo "WARNING: Claude Code install failed; run curl -fsSL https://claude.ai/install.sh | bash as pi"
fi

# STS (Docker) is not started here: its database is restored at swap time first
# (docs/hosts/PI_OS_REBUILD.md, Phase 4).
echo "hart-firstboot done"
