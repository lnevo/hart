#!/usr/bin/env bash
# Export JMRI layout to local xlsx, then push to Google Sheets via NextTrainDispatcherApp credentials.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LAYOUT="${JMRI_LAYOUT:-linear4}"
export JMRI_LAYOUT="$LAYOUT"

echo "==> Export xlsx for layout: $LAYOUT"
python3 "$ROOT/dispatcher/scripts/jmri_layout_to_nexttrain_xlsx.py" --whole-layout

echo "==> Push to Google Sheets (NextTrainDispatcherApp/.env.local)"
cd "$ROOT/NextTrainDispatcherApp"
if [[ -f "$ROOT/.env.local" && ! -f .env.local ]]; then
  cp "$ROOT/.env.local" .env.local
fi
if [[ ! -f .env.local && ! -f "$ROOT/.env.local" ]]; then
  echo "Missing .env.local (Panel root or NextTrainDispatcherApp/) with Google Sheets credentials."
  exit 1
fi
npm install --no-save xlsx 2>/dev/null || npm install
if [[ -f .env.local ]]; then
  npm run push-layout -- --layout "$LAYOUT"
else
  dotenv -e "$ROOT/.env.local" -- node scripts/push-layout-xlsx-to-sheets.js --layout "$LAYOUT"
fi
