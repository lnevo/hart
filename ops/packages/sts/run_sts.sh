#!/usr/bin/env bash
# Optional one-liner — equivalent to sts_compose.sh up -d --build
set -euo pipefail
exec "$(cd "$(dirname "$0")/../../scripts" && pwd)/sts_compose.sh" up -d --build "$@"
