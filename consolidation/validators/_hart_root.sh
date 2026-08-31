#!/usr/bin/env bash
# Resolve HART_LIVE_ROOT for consolidation validators (mirror or live repo fallback).
set -euo pipefail

_HART_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
_RUNTIME="$_HART_REPO/consolidation/external/hart-runtime"

if [[ -z "${HART_LIVE_ROOT:-}" ]]; then
  if [[ -f "$_RUNTIME/jmri/layout_paths.py" ]]; then
    export HART_LIVE_ROOT="$_RUNTIME"
  else
    export HART_LIVE_ROOT="$_HART_REPO"
  fi
fi

export JMRI_LAYOUT="${JMRI_LAYOUT:-hart}"
