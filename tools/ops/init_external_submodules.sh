#!/usr/bin/env bash
# Stage external/ submodules. Run from hart repo root.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
EXT="$ROOT/external"
cd "$ROOT"

LCOS_PIN=ae2d8da7b8821d2b14c889e05063ea359bab6afe
STS_DOCKER_PIN=9ba78c31ef2e8431b2602532d4ce7746b8ebc011
STS_HELPERS_PIN=bb44f2424ccf55d15e16140c159a5421729036d0
STS_PLUGINS_PIN=c3c570ca126e4c73d2eb665b518cbf182c14bacc
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

add_submodule external/lcos-bridge git@github.com:lnevo/LCOS_ESP32_MQTT_Client.git "$LCOS_PIN"
add_submodule external/sts-docker git@github.com:lnevo/sts-docker.git "$STS_DOCKER_PIN"
add_submodule external/sts-helpers git@github.com:lnevo/sts-docker-helpers.git "$STS_HELPERS_PIN"
add_submodule external/sts-plugins git@github.com:lnevo/sts-plugins.git "$STS_PLUGINS_PIN"
add_submodule external/hart-ops git@github.com:lnevo/hart-ops.git "$HART_OPS_PIN"

echo ""
echo "Submodules under external/ only."
git submodule status external/*
