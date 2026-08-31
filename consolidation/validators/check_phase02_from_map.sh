#!/usr/bin/env bash
# Draft D2c: phase02 OS expectations from public_name_map (read-only).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export JMRI_LAYOUT="${JMRI_LAYOUT:-hart}"
python3 consolidation/scripts/check_hart_phase02_from_map.py
