#!/usr/bin/env bash
# Wrap audit_panel_contracts.py --strict (consolidation mirror or live fallback).
set -euo pipefail
# shellcheck source=consolidation/validators/_hart_root.sh
source "$(dirname "$0")/_hart_root.sh"
cd "$HART_LIVE_ROOT"
python3 jmri/layouts/hart/scripts/audit_panel_contracts.py --strict
