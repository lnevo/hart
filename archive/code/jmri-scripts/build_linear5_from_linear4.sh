#!/usr/bin/env bash
# Regenerate linear5 from linear4: Y-spread + A48 arc only (no leveling).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
L4="$ROOT/jmri/layouts/linear4/anyrail/linear4.xml"
L5W="$ROOT/jmri/layouts/linear5/working"
L5="$ROOT/jmri/layouts/linear5"
FACTOR="${1:-4.0}"

python3 "$ROOT/jmri/scripts/spread_layout_y.py" \
  "$L4" \
  "$L5W/linear5_spread_${FACTOR}.xml" \
  --factor "$FACTOR" \
  --layout-name linear5

python3 "$ROOT/jmri/scripts/polish_linear5_geometry.py" \
  "$L5W/linear5_spread_${FACTOR}.xml" \
  "$L5W/linear5_spread_${FACTOR}_arc.xml" \
  --arc-x-scale "$FACTOR"

python3 "$ROOT/jmri/scripts/prepare_tables_from_anyrail.py" \
  "$L5W/linear5_spread_${FACTOR}_arc.xml" \
  "$L5/anyrail/linear5.xml" \
  "$ROOT/jmri/layouts/mac/authoritative/mac_jmri2.xml" \
  --scale 1

cp "$L5/anyrail/linear5.xml" "$L5/authoritative/linear5.xml"

cd "$ROOT/jmri"
JMRI_LAYOUT=linear5 python3 scripts/apply_blocks_to_panel.py \
  layouts/linear5/anyrail/linear5.xml \
  layouts/linear5/output/linear5_blocked_generated.xml \
  layouts/mac/authoritative/mac_jmri2.xml \
  use-panel-layout no-nx

echo "Generated: $L5/output/linear5_blocked_generated.xml"
echo "Manual JMRI save (do not overwrite): $L5/reference/linear5_manual_save.xml"
