#!/usr/bin/env bash
# Deploy layout package from consolidation/external/hart-runtime/ to Pi/Windows.
set -euo pipefail

PKG="$(cd "$(dirname "$0")" && pwd)"
CON="$(cd "$PKG/../.." && pwd)"
RUNTIME="$CON/external/hart-runtime"
SYNC="$RUNTIME/cats/scripts/sync_hart_package.sh"

if [[ -f "$PKG/hosts.env" ]]; then
  # shellcheck source=/dev/null
  source "$PKG/hosts.env"
fi

if [[ ! -f "$SYNC" ]]; then
  echo "Missing $SYNC — run: bash consolidation/scripts/mirror_hart_runtime.sh" >&2
  exit 1
fi

# sync_hart_package.sh resolves ROOT as parents[2] from cats/scripts → hart-runtime
exec bash "$SYNC" "$@"
