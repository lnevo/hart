#!/usr/bin/env bash
# Wrap check_hart_phase02.py (consolidation mirror or live fallback).
set -euo pipefail
# shellcheck source=consolidation/validators/_hart_root.sh
source "$(dirname "$0")/_hart_root.sh"
cd "$HART_LIVE_ROOT"
python3 jmri/scripts/check_hart_phase02.py
