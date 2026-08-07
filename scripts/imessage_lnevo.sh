#!/usr/bin/env bash
# Best-effort iMessage to lnevo@mac.com (may prompt macOS permission once).
# Usage: scripts/imessage_lnevo.sh "message text"
set -euo pipefail
MSG="${1:?message required}"
# Escape for AppleScript
ESC=$(printf '%s' "$MSG" | sed 's/\\/\\\\/g; s/"/\\"/g')
# timeout avoids indefinite hang if Messages waits on UI permission
if command -v gtimeout >/dev/null 2>&1; then
  T=gtimeout
elif command -v timeout >/dev/null 2>&1; then
  T=timeout
else
  T=""
fi
run() {
  osascript -e "tell application \"Messages\" to send \"$ESC\" to buddy \"lnevo@mac.com\""
}
if [[ -n "$T" ]]; then
  "$T" 8 bash -c "$(declare -f run); run" || echo "imessage: timed out or failed (check Messages privacy)" >&2
else
  run || echo "imessage: failed" >&2
fi
