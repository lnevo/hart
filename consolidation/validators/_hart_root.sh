#!/usr/bin/env bash
# Resolve HART_LIVE_ROOT for consolidation validators: the live repo.
set -euo pipefail

_HART_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
_ENV="${_HART_REPO}/consolidation/env/load_consolidation_env.sh"
if [[ -f "$_ENV" ]]; then
  # shellcheck source=consolidation/env/load_consolidation_env.sh
  source "$_ENV"
fi

export HART_LIVE_ROOT="${HART_LIVE_ROOT:-$_HART_REPO}"

export JMRI_LAYOUT="${JMRI_LAYOUT:-hart}"
