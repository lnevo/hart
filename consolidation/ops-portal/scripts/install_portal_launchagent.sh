#!/usr/bin/env bash
# Install a per-user LaunchAgent so the operator portal stays up after
# Cursor/terminal exit, restarts on crash, and comes back at login.
set -euo pipefail

LABEL="com.hart.ops-portal"
PORT="${PORT:-8760}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVE_PY="$SCRIPT_DIR/serve_portal.py"
CONSOL="$(cd "$SCRIPT_DIR/../.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_OUT="$HOME/Library/Logs/hart-ops-portal.log"
LOG_ERR="$HOME/Library/Logs/hart-ops-portal.err.log"
UID_NUM="$(id -u)"
DOMAIN="gui/${UID_NUM}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [install|uninstall|status|restart]

  install    Write ~/Library/LaunchAgents/${LABEL}.plist and start it
  uninstall  Stop the agent and remove the plist
  status     Show launchctl + HTTP check
  restart    Bounce the running agent

PORT=${PORT}  (override with PORT=8760)
EOF
}

python_bin() {
  if [[ -x /opt/homebrew/bin/python3 ]]; then
    echo /opt/homebrew/bin/python3
  elif [[ -x /usr/local/bin/python3 ]]; then
    echo /usr/local/bin/python3
  else
    command -v python3
  fi
}

write_plist() {
  local py
  py="$(python_bin)"
  mkdir -p "$HOME/Library/LaunchAgents" "$(dirname "$LOG_OUT")"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${py}</string>
    <string>${SERVE_PY}</string>
    <string>${PORT}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${CONSOL}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>5</integer>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>${LOG_OUT}</string>
  <key>StandardErrorPath</key>
  <string>${LOG_ERR}</string>
</dict>
</plist>
EOF
}

is_loaded() {
  launchctl print "${DOMAIN}/${LABEL}" >/dev/null 2>&1
}

bootout() {
  if is_loaded; then
    launchctl bootout "${DOMAIN}/${LABEL}" >/dev/null 2>&1 || true
  fi
}

bootstrap() {
  launchctl bootstrap "$DOMAIN" "$PLIST"
  launchctl enable "${DOMAIN}/${LABEL}" >/dev/null 2>&1 || true
}

http_ok() {
  curl -fsS -o /dev/null -w "%{http_code}" --max-time 2 "http://127.0.0.1:${PORT}/ops-portal/"
}

cmd_status() {
  if is_loaded; then
    echo "LaunchAgent: loaded (${DOMAIN}/${LABEL})"
    launchctl print "${DOMAIN}/${LABEL}" 2>/dev/null | awk '
      /state = / { print "  " $0 }
      /pid = / { print "  " $0 }
      /runs = / { print "  " $0 }
    '
  else
    echo "LaunchAgent: not loaded"
  fi
  if [[ -f "$PLIST" ]]; then
    echo "Plist: $PLIST"
  else
    echo "Plist: missing"
  fi
  local code
  if code="$(http_ok)"; then
    echo "HTTP: ${code}  http://127.0.0.1:${PORT}/ops-portal/"
  else
    echo "HTTP: not responding on 127.0.0.1:${PORT}"
  fi
}

cmd_install() {
  if [[ ! -f "$SERVE_PY" ]]; then
    echo "missing $SERVE_PY" >&2
    exit 1
  fi
  bootout
  write_plist
  bootstrap
  # launchd can take a beat to bind the port
  local i code=""
  for i in 1 2 3 4 5 6 7 8; do
    if code="$(http_ok 2>/dev/null)"; then
      break
    fi
    sleep 0.25
  done
  echo "Installed ${LABEL} (KeepAlive + RunAtLoad)."
  echo "Portal → http://127.0.0.1:${PORT}/ops-portal/"
  echo "Logs   → ${LOG_OUT}"
  cmd_status
  if [[ -z "${code}" ]]; then
    echo "warning: agent loaded but HTTP not up yet; check ${LOG_ERR}" >&2
    exit 1
  fi
}

cmd_uninstall() {
  bootout
  rm -f "$PLIST"
  echo "Removed ${LABEL}."
}

cmd_restart() {
  if [[ ! -f "$PLIST" ]]; then
    echo "not installed; run: $0 install" >&2
    exit 1
  fi
  bootout
  bootstrap
  echo "Restarted ${LABEL}."
  cmd_status
}

case "${1:-install}" in
  install) cmd_install ;;
  uninstall) cmd_uninstall ;;
  status) cmd_status ;;
  restart) cmd_restart ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 2 ;;
esac
