#!/usr/bin/env bash
# Draft D2c: phase02 OS expectations from public_name_map.
set -euo pipefail
HART_REPO="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=consolidation/validators/_hart_root.sh
source "$(dirname "$0")/_hart_root.sh"
cd "$HART_LIVE_ROOT"
python3 "$HART_REPO/consolidation/scripts/check_hart_phase02_from_map.py"
