#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${HART_STS_HELPERS:-}" && -d "$HART_STS_HELPERS/bin" ]]; then
  echo "$HART_STS_HELPERS"
  exit 0
fi

_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ops/hart-ops → the hart repo's external/sts-helpers submodule
if [[ -d "$_HERE/../../external/sts-helpers/bin" ]]; then
  echo "$(cd "$_HERE/../../external/sts-helpers" && pwd)"
  exit 0
fi

echo "Set HART_STS_HELPERS to sts-docker-helpers clone" >&2
exit 1
