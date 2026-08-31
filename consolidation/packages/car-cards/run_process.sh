#!/usr/bin/env bash
# Run car image batch pipeline from consolidation workspace.
set -euo pipefail

PKG="$(cd "$(dirname "$0")" && pwd)"
CON="$(cd "$PKG/../.." && pwd)"
CAR="${HART_CAR_CARDS_ROOT:-$CON/external/desktop-data/car-cards}"
HOPS="$CON/external/hart-ops"
FINAL="${HART_CAR_IMAGES_FINAL:-$CON/external/desktop-data/car-images/CarImagesFinal}"

export HART_CAR_CARDS_ROOT="$CAR"
export HART_CAR_IMAGES_FINAL="$FINAL"

bash "$CON/scripts/setup_car_cards_workspace.sh" >/dev/null

cd "$HOPS"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

echo "Car cards root: $CAR"
echo "Drop raws in: $CAR/incoming/"
.venv/bin/python card_pipeline/process_car_images.py "$@"
