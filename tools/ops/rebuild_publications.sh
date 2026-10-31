#!/usr/bin/env bash
# Regenerate the publications in docs/ops with the hart-ops scripts.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOPS="$ROOT/external/hart-ops"
cd "$HOPS"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

PY=.venv/bin/python
DOCS="$ROOT/docs/ops"

SCRIPTS=(
  publications/rebuild_scale_operating_instructions.py
  publications/rebuild_dispatcher_train_list.py
  publications/rebuild_yardmaster_sequence.py
  publications/rebuild_crew_instructions.py
  publications/rebuild_station_map.py
  publications/rebuild_local_station_maps.py
  publications/rebuild_operator_primer.py
  publications/update_tt23_station_map.py
)

echo "=== Pipeline 15 — publications rebuild ==="
for s in "${SCRIPTS[@]}"; do
  echo "--- $s ---"
  "$PY" "$s"
done

echo "Outputs: $DOCS/"
ls -1 "$DOCS"/*.docx 2>/dev/null | wc -l | xargs echo "docx in docs/ops:"
