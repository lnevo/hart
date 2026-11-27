#!/usr/bin/env bash
# Deploy step 2: build the host packages once, into a folder. Nothing leaves this machine and nothing outside
# the folder is written.
#
# Usage: stage.sh [--pi] [--win] DIR     (no host flag builds both)
#   DIR/pi   the Pi's package         DIR/win   Windows' package
#
# The package is what lands in a temporary folder on a host; the apply scripts install it from there.
# Hosts are not git clones. Panels are path-rewritten per user-files, and the payload is a subset (no wiki,
# screenshots, linear layouts, or CATS src). The repo keeps the host scripts in tools/hosts/pi and
# tools/hosts/windows; the package still carries them at cats/scripts/pi and cats/scripts/windows, as the hosts
# expect. The Pi and Windows packages differ only in the panels (their icon paths name the host's user files)
# and the stamp's target, so stage_package builds the rest once and stage_host_finish adds those two per host.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
STAGE_DIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pi) DO_PI=1 ;;
    --win) DO_WIN=1 ;;
    -*) echo "stage.sh: unknown option: $1" >&2; exit 1 ;;
    *) [[ -z "$STAGE_DIR" ]] || { echo "stage.sh: one folder only" >&2; exit 1; }; STAGE_DIR="$1" ;;
  esac
  shift
done
[[ -n "$STAGE_DIR" ]] || { echo "Usage: stage.sh [--pi] [--win] DIR" >&2; exit 1; }
[[ "$DO_PI" -eq 1 || "$DO_WIN" -eq 1 ]] || { DO_PI=1; DO_WIN=1; }

load_parked
deploy_facts
tables_facts

# Finder litter is never copied: an rsync that skips it never reads a .DS_Store that vanishes while it copies (a
# test plants and removes them in the checkout; rsync then stops with code 24). The find -delete below still clears
# what a cp step brings.
LITTER_EXCLUDES=(--exclude '.DS_Store' --exclude '._*')

stage_package() {
  local stage="$1"
  rm -rf "$stage"
  mkdir -p \
    "$stage/cats/panels" \
    "$stage/cats/resources/buttons" \
    "$stage/cats/resources/icons/USS/sensor" \
    "$stage/cats/resources/misc" \
    "$stage/cats/resources/roster" \
    "$stage/cats/scripts" \
    "$stage/jmri/layouts/hart/scripts" \
    "$stage/jmri/scripts"

  local f
  for f in "$ROOT/jmri/resources/buttons/"lamp_*.png \
           "$ROOT/jmri/resources/buttons/"triangle_*.png; do
    [[ -f "$f" ]] && cp -f "$f" "$stage/cats/resources/buttons/"
  done
  if [[ -d "$ROOT/jmri/resources/icons/USS/sensor" ]]; then
    cp -f "$ROOT/jmri/resources/icons/USS/sensor/"yellow-*.gif \
      "$stage/cats/resources/icons/USS/sensor/" 2>/dev/null || true
  fi
  if [[ -d "$ROOT/jmri/resources/roster" ]]; then
    cp -f "$ROOT/jmri/resources/roster/"*.jpg "$stage/cats/resources/roster/" 2>/dev/null || true
  fi

  cp -f "$ROOT/jmri/resources/misc/"* "$stage/cats/resources/misc/"

  rsync -a "${LITTER_EXCLUDES[@]}" "$ROOT/jmri/resources/jmri-web/" "$stage/cats/resources/jmri-web/"
  python3 "$ROOT/tools/mqtt-mimic/build_mimic_web.py" --out "$stage/cats/resources/jmri-web/mimic"
  # Speed-match live view for the Pi (/web/speedmatch/): the page, and the publisher with the
  # files it reads, laid out as in the repo (scripts/speedmatch, data/block_lengths.csv with
  # block_lengths_measured.csv beside it, and the 2026-11-08 reference speeds).
  local sm="$ROOT/jmri/layouts/hart/scripts/speedmatch"
  python3 "$sm/dashboard/publish_live.py" --build-page "$stage/cats/resources/speedmatch-web" >/dev/null
  mkdir -p "$stage/cats/speedmatch-live/scripts/speedmatch/dashboard" "$stage/cats/speedmatch-live/data"
  cp -f "$sm/analyze.py" "$sm/analyze_records.py" "$sm/liverule.py" "$sm/routes.json" \
    "$stage/cats/speedmatch-live/scripts/speedmatch/"
  cp -f "$sm/dashboard/dashstate.py" "$sm/dashboard/dashsources.py" "$sm/dashboard/export_site_runs.py" \
    "$sm/dashboard/publish_live.py" "$stage/cats/speedmatch-live/scripts/speedmatch/dashboard/"
  cp -f "$ROOT/jmri/layouts/hart/data/block_lengths.csv" "$ROOT/jmri/layouts/hart/data/block_lengths_measured.csv" \
    "$ROOT/jmri/layouts/hart/data/speed_by_step_2026-11-08.csv" \
    "$stage/cats/speedmatch-live/data/"
  # Host scripts live in tools/hosts/ but land where the hosts and their shortcuts expect them (ADR-007).
  rsync -a "${LITTER_EXCLUDES[@]}" "$ROOT/tools/hosts/pi/" "$stage/cats/scripts/pi/"
  rsync -a "${LITTER_EXCLUDES[@]}" "$ROOT/tools/hosts/windows/" "$stage/cats/scripts/windows/"
  cp -f "$ROOT/cats/scripts/install_jmri_web_override.sh" \
    "$ROOT/cats/scripts/rewrite_button_icon_paths.py" \
    "$ROOT/cats/scripts/patch_jmri_startup.py" \
    "$ROOT/cats/scripts/install_ops_files.sh" \
    "$ROOT/tools/hosts/panel_window_sizes.py" \
    "$stage/cats/scripts/"
  # The part of hartlib the two profile scripts above import (hartlib.jmri_profile), where their own search for
  # tools/hartlib/src finds it. The rest of hartlib needs a checkout (hartlib.paths) and stays out.
  mkdir -p "$stage/tools/hartlib/src/hartlib"
  cp -f "${HARTLIB_HOST_MODULES[@]/#/$ROOT/tools/hartlib/src/hartlib/}" "$stage/tools/hartlib/src/hartlib/"
  # JMRI's MQTT race overlay until JMRI/JMRI#16004 reaches a release the hosts run (ADR-034).
  mkdir -p "$stage/jmri/mqtt_overlay"
  cp -f "$ROOT/tools/jmri/mqtt_overlay/hart-mqtt-race-fix.jar" \
    "$ROOT/tools/jmri/mqtt_overlay/install_overlay.py" "$stage/jmri/mqtt_overlay/"

  for f in "${HART_JYTHON_SCRIPTS[@]}"; do
    [[ -f "$ROOT/$f" ]] && cp -f "$ROOT/$f" "$stage/$(dirname "$f")/"
  done
  cp -f "$ROOT/jmri/scripts/signal_coordinator.py" "${JYTHON_SIBLING_MODULES[@]}" "$stage/jmri/scripts/"
  cp -f "${JYTHON_PANEL_STATUS_PARTS[@]}" "$stage/jmri/layouts/hart/scripts/"

  # A parked feature's folder is left out of the package; the host apply scripts install only what the package
  # holds, so the copies already on a host stay as they are.
  local traininfo="$ROOT/jmri/layouts/hart/dispatcher/traininfo"
  if ! parked_dir jmri/layouts/hart/dispatcher; then
    mkdir -p "$stage/jmri/layouts/hart/dispatcher"
    if [[ -d "$traininfo" ]]; then
      rsync -a "${LITTER_EXCLUDES[@]}" "$traininfo/" "$stage/jmri/layouts/hart/dispatcher/traininfo/"
    fi
    if [[ -f "$ROOT/jmri/layouts/hart/dispatcher/dispatcheroptions.xml" ]]; then
      cp -f "$ROOT/jmri/layouts/hart/dispatcher/dispatcheroptions.xml" \
        "$stage/jmri/layouts/hart/dispatcher/"
    fi
  fi

  if ! parked_dir jmri/layouts/hart/ctc && [[ -d "$ROOT/jmri/layouts/hart/ctc/icons" ]]; then
    mkdir -p "$stage/ctc/icons"
    rsync -a "${LITTER_EXCLUDES[@]}" "$ROOT/jmri/layouts/hart/ctc/icons/" "$stage/ctc/icons/"
    [[ -f "$ROOT/jmri/layouts/hart/ctc/GUIObjects.xml" ]] && \
      cp -f "$ROOT/jmri/layouts/hart/ctc/GUIObjects.xml" "$stage/ctc/"
  fi
  if [[ -n "$TABLES" ]]; then
    cp -f "$TABLES" "$stage/tables.xml"
  fi
  mkdir -p "$stage/operations"
  cp -f "$ROOT/jmri/layouts/hart/operations/"*.xml "$stage/operations/"
  # The DecoderPro roster (ADR-039 amendment 2026-11-26): roster.xml and the entry files it names, as the hosts keep
  # them under JMRI_UserFiles (tools/hosts/pi/install_roster.sh and the Windows apply install it). A master that
  # names a file it lacks stops the staging, so the gate's trial staging (G7) stops the deploy.
  local roster_names name
  roster_names="$(source "$ROOT/tools/hosts/pi/roster_sha.sh" && roster_files "$ROSTER_MASTER")" \
    || { echo "stage.sh: cannot read the DecoderPro roster master $ROSTER_MASTER/roster.xml" >&2; exit 1; }
  [[ -n "$roster_names" ]] || { echo "stage.sh: $ROSTER_MASTER/roster.xml names no locomotive file" >&2; exit 1; }
  mkdir -p "$stage/roster/roster"
  cp -f "$ROSTER_MASTER/roster.xml" "$stage/roster/"
  while IFS= read -r name; do
    [[ -f "$ROSTER_MASTER/roster/$name" ]] \
      || { echo "stage.sh: $ROSTER_MASTER/roster.xml names roster/$name, which is not there" >&2; exit 1; }
    cp -f "$ROSTER_MASTER/roster/$name" "$stage/roster/roster/"
  done <<<"$roster_names"
  chmod +x "$stage/cats/scripts/pi/"*.sh "$stage/cats/scripts/"*.sh 2>/dev/null || true
  # Finder litter (.DS_Store, AppleDouble) from a gitignored corner of the checkout must not reach the package,
  # whichever copy step brought it.
  find "$stage" \( -name '.DS_Store' -o -name '._*' \) -type f -delete
}

# stage_host_finish STAGE USER_FILES TARGET: the panels rewritten for the host, then its stamp.
stage_host_finish() {
  local stage="$1" user_files="$2" target="$3" p
  for p in "${LIVE_PANELS[@]}"; do
    python3 "$REWRITE" --panel "$ROOT/cats/panels/$p" \
      --user-files "$user_files" --out "$stage/cats/panels/$p"
  done
  # The host apply scripts install this last, so it only changes once a deploy has finished.
  write_deploy_stamp "$stage/cats/deploy_stamp.txt" "$target"
}

# stage_hosts DIR: DIR/pi and DIR/win for the hosts named, from one staged build.
stage_hosts() {
  local dir="$1" first=pi
  [[ "$DO_PI" -eq 1 ]] || first=win
  stage_package "$dir/$first"
  if [[ "$DO_PI" -eq 1 && "$DO_WIN" -eq 1 ]]; then
    rsync -a "${LITTER_EXCLUDES[@]}" "$dir/pi/" "$dir/win/"
  fi
  [[ "$DO_PI" -eq 0 ]] || stage_host_finish "$dir/pi" "$PI_USERFILES" pi
  [[ "$DO_WIN" -eq 0 ]] || stage_host_finish "$dir/win" "$WIN_USERFILES" win
}

mkdir -p "$STAGE_DIR"
stage_hosts "$STAGE_DIR"
