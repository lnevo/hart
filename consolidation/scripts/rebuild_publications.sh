#!/usr/bin/env bash
# Regenerate all pipeline-15 publications from hart-ops (consolidation workspace).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOPS="$ROOT/consolidation/external/hart-ops"
cd "$HOPS"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

PY=.venv/bin/python
PUB="$HOPS/docs/published"

# Rebuild scripts read masthead templates from docs/ (not docs/published/).
link_template() {
  local name="$1"
  local src="$PUB/$name"
  local dest="$HOPS/docs/$name"
  if [[ -f "$src" && ! -f "$dest" ]]; then
    (cd "$HOPS/docs" && ln -sf "published/$name" "$name")
  fi
}

for f in \
  "HART Railroad Scale Operating Instructions.docx" \
  Neville_Island_Dispatcher_Train_List.docx \
  Neville_Island_Yardmaster_Sequence.docx \
  Neville_Island_Crew_D749.docx \
  Neville_Island_Crew_NVL.docx \
  Neville_Island_Crew_CK1.docx \
  Neville_Island_Station_Map.docx \
  Neville_Island_New_Operator_Primer.docx \
  Toggle_Dimensions.png \
  TT-23_Route23_NevilleQueen_RevisionA_v6.pptx \
  ; do
  link_template "$f"
done

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

echo "Outputs: $HOPS/docs/ (and docs/published/ archive)"
ls -1 "$HOPS/docs"/*.docx 2>/dev/null | wc -l | xargs echo "docx in docs/:"
ls -1 "$PUB"/*.docx 2>/dev/null | wc -l | xargs echo "docx in published/:"
