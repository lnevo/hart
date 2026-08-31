#!/usr/bin/env bash
# Regenerate print templates and waybill decks from consolidation workspace.
set -euo pipefail

PKG="$(cd "$(dirname "$0")" && pwd)"
CON="$(cd "$PKG/../.." && pwd)"
HOPS="$CON/external/hart-ops"
CAR="${HART_CAR_CARDS_ROOT:-$CON/external/desktop-data/car-cards}"

export HART_CAR_CARDS_ROOT="$CAR"
export HART_CAR_IMAGES_FINAL="${HART_CAR_IMAGES_FINAL:-$CON/external/desktop-data/car-images/CarImagesFinal}"

bash "$CON/scripts/setup_car_cards_workspace.sh" >/dev/null

cd "$HOPS"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

echo "=== equipment card template ==="
.venv/bin/python card_pipeline/generate_card_template.py

echo "=== spot waybills ==="
.venv/bin/python card_pipeline/generate_waybill_cards.py

if [[ "${GENERATE_ALL_CARDS:-0}" == "1" ]]; then
  echo "=== full fleet (large) ==="
  .venv/bin/python card_pipeline/generate_all_cards.py
fi

echo "Print outputs: $HOPS/card_pipeline/output/"
ls -lah "$HOPS/card_pipeline/output/"
