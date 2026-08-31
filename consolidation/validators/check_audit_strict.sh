#!/usr/bin/env bash
# Wrap live audit_panel_contracts.py --strict (read-only on live XML).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export JMRI_LAYOUT="${JMRI_LAYOUT:-hart}"
python3 jmri/layouts/hart/scripts/audit_panel_contracts.py --strict
