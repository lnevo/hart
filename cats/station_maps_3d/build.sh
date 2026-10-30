#!/usr/bin/env bash
# Export the Barn station map plate: one STL per colour, then barn.3mf to print from.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OPENSCAD="${OPENSCAD:-/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD}"
SRC="$HERE/station_map_barn.scad"
OUT="$HERE/stl"
mkdir -p "$OUT"

for part in white black teal gold; do
  "$OPENSCAD" -D "part=\"$part\"" -o "$OUT/barn_$part.stl" "$SRC"
done

python3 "$HERE/make_3mf.py"
