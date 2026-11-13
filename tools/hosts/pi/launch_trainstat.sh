#!/usr/bin/env bash
# Launch TrainStat (yard/trainmaster client) against CATS on this Pi.
# CATS must be running with Start TrainStat Server enabled (panel has <TRAINSTATLABEL />).
set -euo pipefail
TS_HOME="${TS_HOME:-/home/pi/JMRI_UserFiles/cats/trainstat}"
CONFIG="${1:-$TS_HOME/hart_trainstat.xml}"
LOG="${TRAINSTAT_LAUNCH_LOG:-/home/pi/JMRI_UserFiles/cats/logs/trainstat_launch.log}"

if [[ ! -f "$TS_HOME/TrainStat.jar" ]]; then
  echo "TrainStat not installed in $TS_HOME" >&2
  exit 1
fi
if [[ ! -f "$CONFIG" ]]; then
  echo "Config not found: $CONFIG" >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG")"
: >"$LOG"
echo "JAVA: $(java -version 2>&1 | head -1)" | tee -a "$LOG"
echo "TS_HOME=$TS_HOME" | tee -a "$LOG"
echo "Config=$CONFIG" | tee -a "$LOG"

cd "$TS_HOME"
OPTS=("CONFIGURATION=$CONFIG")
if [[ "${TRAINSTAT_TRACE:-}" == "1" ]]; then
  OPTS+=("TRACE")
fi
exec java -noverify \
  -Dswing.defaultlaf=javax.swing.plaf.metal.MetalLookAndFeel \
  -Dswing.metalTheme=ocean \
  -cp ".:TrainStat.jar:lib/log4j.jar:lib/jdom.jar" \
  trainStat.TrainStat \
  "${OPTS[@]}" \
  2>&1 | tee -a "$LOG"
