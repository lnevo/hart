#!/usr/bin/env bash
# Refresh all consolidation mirrors from live (read-only sources).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "=== mirror STS runtime data ==="
bash consolidation/scripts/mirror_sts_docker_data.sh

echo
echo "=== mirror HART layout ops tree ==="
bash consolidation/scripts/mirror_hart_runtime.sh

echo
echo "=== mirror Desktop/HART operational data ==="
bash consolidation/scripts/mirror_desktop_data.sh

echo
echo "=== snapshot SoR CSVs ==="
python3 consolidation/scripts/snapshot_live_sor.py

echo
echo "=== rebuild wiring crosswalk ==="
python3 consolidation/scripts/build_wiring_crosswalk.py

echo
echo "=== setup car cards workspace ==="
bash consolidation/scripts/setup_car_cards_workspace.sh

echo
echo "=== run validators ==="
bash consolidation/validators/run_all.sh

echo
echo "All mirrors refreshed."
