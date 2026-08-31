#!/usr/bin/env bash
# Stage consolidation/external/ submodules. Run from hart repo root.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
EXT="$ROOT/consolidation/external"
cd "$ROOT"

LCOS_PIN=ae2d8da7b8821d2b14c889e05063ea359bab6afe
STS_DOCKER_PIN=899b45809c99b92614f99990a88fee1dd4e63be2
STS_HELPERS_PIN=31b8583851482d270f45c233f67190d0d8b80c10
HART_OPS_PIN=0fecf5ecf6195b03048f0829fc4b00ee223bc521

mkdir -p "$EXT"

add_submodule() {
  local path="$1" url="$2" pin="$3"
  if [[ -d "$path/.git" ]] || grep -q "path = $path" .gitmodules 2>/dev/null; then
    echo "SKIP $path (already present)"
    git -C "$path" checkout "$pin" 2>/dev/null || true
    return 0
  fi
  git submodule add "$url" "$path"
  git -C "$path" checkout "$pin"
  echo "OK $path @ $pin"
}

add_submodule consolidation/external/lcos-bridge git@github.com:lnevo/LCOS_ESP32_MQTT_Client.git "$LCOS_PIN"
add_submodule consolidation/external/sts-docker git@github.com:lnevo/sts-docker.git "$STS_DOCKER_PIN"
add_submodule consolidation/external/sts-helpers git@github.com:lnevo/sts-docker-helpers.git "$STS_HELPERS_PIN"
add_submodule consolidation/external/hart-ops git@github.com:lnevo/hart-ops.git "$HART_OPS_PIN"

echo ""
echo "Submodules under consolidation/external/ only."
git submodule status consolidation/external/*
