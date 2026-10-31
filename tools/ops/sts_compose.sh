#!/usr/bin/env bash
# Optional shortcut — refresh compose paths then run docker compose.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
bash "${SCRIPT_DIR}/refresh_sts_docker_compose.sh"
# shellcheck source=../env/load_env.sh
source "${SCRIPT_DIR}/../env/load_env.sh"
cd "${STS_DOCKER_ROOT}"
exec docker compose --profile build "$@"
