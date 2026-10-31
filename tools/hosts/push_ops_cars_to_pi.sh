#!/usr/bin/env bash
# Install the Operations Pro roster merged by `cars.py publish` on the Pi.
# Run sync_roster_ops_from_pi.sh --mac first, and publish again, so the merge
# starts from the Pi's current session state. JMRI must be closed on the Pi.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PI_HOST="${HART_PI_SSH:-pi}"
SRC="$ROOT/external/hart-ops/card_pipeline/output/ops_merge/OperationsCarRoster.xml"
DEST="/home/pi/JMRI_UserFiles/operations/OperationsCarRoster.xml"

[[ -f "$SRC" ]] || { echo "Missing $SRC. Run cars.py publish first." >&2; exit 1; }
if ssh "$PI_HOST" pgrep -f 'jmri|apps.PanelPro|cats' >/dev/null; then
  echo "JMRI is running on the Pi. Close it first; it would overwrite this file." >&2
  exit 1
fi
stamp="$(date +%Y%m%d_%H%M%S)"
ssh "$PI_HOST" cp "$DEST" "$DEST.pre_cars_$stamp"
scp "$SRC" "$PI_HOST:$DEST"
echo "Installed on the Pi; backup is $DEST.pre_cars_$stamp"
echo "Now run: cars.py publish --mark-ops"
