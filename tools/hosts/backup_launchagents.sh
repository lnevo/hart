#!/usr/bin/env bash
# Install, remove or check the Mac's two backup LaunchAgents (ADR-035).
#
#   com.hart.backup-pi   daily at 03:30: tools/hosts/backup_pi_pull.sh (Pi data and the STS dump to the Mac)
#   com.hart.backup-win  Sundays at 04:30: tools/hosts/backup_win_push.sh (the Mac's data to the Windows box)
#
# A Mac asleep at that time runs the job when it wakes. The jobs run the scripts in the main
# checkout, so they follow main. Logs: ~/Library/Logs/hart-backup-{pi,win}.log.
#
#   install    write both plists and load them
#   uninstall  unload them and remove the plists
#   status     loaded or not, and the time of each last full run, with a warning when one is overdue
#   run        start both now (the scheduled run is unchanged)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
MAIN="$(dirname "$(git -C "$HERE" rev-parse --path-format=absolute --git-common-dir)")"
ROOT="${HART_BACKUP_DIR:-$HOME/Backups/hart}"
AGENTS="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
PATH_FOR_JOBS="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"  # Homebrew rsync 3 first

# label|script|calendar keys|last-ok file|days before it is overdue
JOBS=(
  "com.hart.backup-pi|backup_pi_pull.sh|<key>Hour</key><integer>3</integer><key>Minute</key><integer>30</integer>|$ROOT/pi/last-ok|2"
  "com.hart.backup-win|backup_win_push.sh|<key>Weekday</key><integer>0</integer><key>Hour</key><integer>4</integer><key>Minute</key><integer>30</integer>|$ROOT/win-last-ok|9"
)

field() { echo "$1" | cut -d'|' -f"$2"; }

plist() {  # <label> <script> <calendar keys> <log name>
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$1</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$MAIN/tools/hosts/$2</string></array>
  <key>StartCalendarInterval</key><dict>$3</dict>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$PATH_FOR_JOBS</string></dict>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/$4.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/$4.log</string>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF
}

status() {
  local rc=0 entry label file days loaded when age
  for entry in "${JOBS[@]}"; do
    label="$(field "$entry" 1)" file="$(field "$entry" 4)" days="$(field "$entry" 5)"
    if launchctl print "$DOMAIN/$label" >/dev/null 2>&1; then loaded=loaded; else loaded="NOT LOADED"; rc=1; fi
    if [[ -f "$file" ]]; then
      when="$(cat "$file")"
      if ! epoch="$(date -j -f '%Y-%m-%d %H:%M:%S' "$when" +%s 2>/dev/null)"; then
        echo "$label: $loaded; last-ok file $file is unreadable ('$when')"; rc=1; continue
      fi
      age=$(( ($(date +%s) - epoch) / 86400 ))
      if (( age >= days )); then
        echo "$label: $loaded; last full run $when, $age days ago: OVERDUE (expected within $days days)"; rc=1
      else
        echo "$label: $loaded; last full run $when"
      fi
    else
      echo "$label: $loaded; no full run yet"; rc=1
    fi
  done
  return "$rc"
}

case "${1:-}" in
  install)
    mkdir -p "$AGENTS" "$HOME/Library/Logs"
    for entry in "${JOBS[@]}"; do
      label="$(field "$entry" 1)" script="$(field "$entry" 2)"
      [[ -x "$MAIN/tools/hosts/$script" ]] || { echo "backup_launchagents: $MAIN/tools/hosts/$script is missing; merge the backup scripts to main first" >&2; exit 2; }
      log="hart-backup-${label##*.backup-}"
      plist "$label" "$script" "$(field "$entry" 3)" "$log" > "$AGENTS/$label.plist"
      plutil -lint -s "$AGENTS/$label.plist"
      launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
      launchctl bootstrap "$DOMAIN" "$AGENTS/$label.plist"
      echo "installed $label"
    done
    ;;
  uninstall)
    for entry in "${JOBS[@]}"; do
      label="$(field "$entry" 1)"
      launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
      rm -f "$AGENTS/$label.plist"
      echo "removed $label"
    done
    ;;
  status) status ;;
  plist)  # print the plists (tests)
    for entry in "${JOBS[@]}"; do
      label="$(field "$entry" 1)"
      plist "$label" "$(field "$entry" 2)" "$(field "$entry" 3)" "hart-backup-${label##*.backup-}"
    done
    ;;
  run)
    for entry in "${JOBS[@]}"; do
      label="$(field "$entry" 1)"
      launchctl kickstart "$DOMAIN/$label" && echo "started $label"
    done
    ;;
  *) echo "usage: $(basename "$0") install|uninstall|status|run" >&2; exit 2 ;;
esac
