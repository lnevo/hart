#!/usr/bin/env bash
# Export the station map plates and test panels: one STL per colour.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OPENSCAD="${OPENSCAD:-/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD}"
OUT="$HERE/stl"
mkdir -p "$OUT"

for part in white black teal gold; do
  "$OPENSCAD" -D "part=\"$part\"" -o "$OUT/barn_$part.stl" "$HERE/station_map_barn.scad"
done

for part in body ink; do
  "$OPENSCAD" -D "part=\"$part\"" -o "$OUT/sw13_$part.stl" "$HERE/toggle_test_sw13.scad"
done

python3 "$HERE/check_stl.py" "$OUT"/barn_*.stl "$OUT"/sw13_*.stl
