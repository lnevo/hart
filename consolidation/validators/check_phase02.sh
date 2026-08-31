#!/usr/bin/env bash
# Wrap live check_hart_phase02.py (read-only).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export JMRI_LAYOUT="${JMRI_LAYOUT:-hart}"
python3 jmri/scripts/check_hart_phase02.py
