#!/usr/bin/env bash
# Stage external/ submodules for hart meta-repo (P3b).
# Run from hart repo root. Requires network + git write access.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

LCOS_PIN=ec16af8c85a5d8c9acb05eed854a5b69cc8ca90d
STS_DOCKER_PIN=899b45809c99b92614f99990a88fee1dd4e63be2
STS_HELPERS_PIN=cdbbfce8ab2ef915430b8e3eafc31267b518cde5

mkdir -p external

add_submodule() {
  local path="$1" url="$2" pin="$3"
  if [[ -d "$path/.git" ]] || grep -q "path = $path" .gitmodules 2>/dev/null; then
    echo "SKIP $path (already present)"
    return 0
  fi
  git submodule add "$url" "$path"
  git -C "$path" checkout "$pin"
  echo "OK $path @ $pin"
}

add_submodule external/lcos-bridge git@github.com:lnevo/LCOS_ESP32_MQTT_Client.git "$LCOS_PIN"
add_submodule external/sts-docker git@github.com:lnevo/sts-docker.git "$STS_DOCKER_PIN"
add_submodule external/sts-helpers git@github.com:lnevo/sts-docker-helpers.git "$STS_HELPERS_PIN"
add_submodule external/hart-ops git@github.com:lnevo/hart-ops.git bc6ce5517b407a4cae62f2c7150f1d96b1735503

if [[ ! -f external/hart-ops/README.md ]]; then
  mkdir -p external/hart-ops
  cat > external/hart-ops/README.md <<'EOF'
# hart-ops — missing submodule

Run: bash consolidation/scripts/init_external_submodules.sh
EOF
  echo "OK external/hart-ops placeholder (run init script)"
fi

echo ""
echo "Done. Review: git submodule status"
echo "Commit .gitmodules + external/* when ready."
