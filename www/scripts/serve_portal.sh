#!/usr/bin/env bash
# Serve the operator portal (JSON fetch needs HTTP, not file://).
# Prefer the login LaunchAgent so this survives Cursor/terminal exit:
#   ./www/scripts/install_portal_launchagent.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8760}"
URL="http://127.0.0.1:${PORT}/www/"
if curl -fsS -o /dev/null --max-time 1 "$URL" 2>/dev/null; then
  echo "Already serving → $URL"
  exit 0
fi
cd "$ROOT"
exec python3 "$ROOT/scripts/serve_portal.py" "$PORT"
