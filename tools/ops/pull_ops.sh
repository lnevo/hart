#!/usr/bin/env bash
# Bring the Pi's Operations Pro session state back into the repo (ADR-015).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$ROOT/tools/env/load_env.sh"  # hosts: environment, hart.env, default
PI_HOST="$HART_PI_SSH"
PI_DIR="$HART_PI_USERFILES/operations"
DEST="$ROOT/jmri/layouts/hart/operations"
FILES=(Operations.xml OperationsCarRoster.xml OperationsEngineRoster.xml
       OperationsLocationRoster.xml OperationsRouteRoster.xml OperationsTrainRoster.xml)

# The brackets stop the pattern matching this command's own shell.
if ssh "$PI_HOST" "pgrep -f '[a]pps.PanelPro|[a]pps.gui3.dp3.DecoderPro3|[a]pps.DecoderPro|[c]ats.apps.Crandic'" >/dev/null; then
  echo "Quit JMRI and CATS on the Pi first." >&2
  exit 1
fi
for f in "${FILES[@]}"; do
  scp -q "$PI_HOST:$PI_DIR/$f" "$DEST/$f"
done
ssh "$PI_HOST" "cd '$PI_DIR' && cat ${FILES[*]} | sha256sum | cut -d' ' -f1 >.deployed.sha256"
git -C "$ROOT" status --short -- "$DEST"
echo "Operations files -> $DEST. Commit any changes."
