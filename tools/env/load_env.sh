#!/usr/bin/env bash
# Resolve repo paths for shell scripts. Source from tools/ops/*.sh:
#   source "$(dirname "$0")/../env/load_env.sh"
# Overrides: copy hart.env.example to hart.env, or export variables before sourcing.

_hart_env_loaded="${_hart_env_loaded:-}"
if [[ -n "$_hart_env_loaded" ]]; then
  return 0 2>/dev/null || exit 0
fi
_hart_env_loaded=1

_env_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export HART_REPO_ROOT="${HART_REPO_ROOT:-$(cd "${_env_dir}/../.." && pwd)}"

_env_file="${HART_ENV_FILE:-${_env_dir}/hart.env}"
if [[ -f "$_env_file" ]]; then
  # shellcheck disable=SC1090
  source "$_env_file"
fi

export HART_RUNTIME_ROOT="${HART_RUNTIME_ROOT:-${HART_REPO_ROOT}}"
export HART_LIVE_ROOT="${HART_LIVE_ROOT:-${HART_REPO_ROOT}}"
export HART_OPS_ROOT="${HART_OPS_ROOT:-${HART_REPO_ROOT}/external/hart-ops}"
export LCOS_BRIDGE_ROOT="${LCOS_BRIDGE_ROOT:-${HART_REPO_ROOT}/external/lcos-bridge}"
export STS_DOCKER_ROOT="${STS_DOCKER_ROOT:-${HART_REPO_ROOT}/external/sts-docker}"
export STS_HELPERS_ROOT="${STS_HELPERS_ROOT:-${HART_REPO_ROOT}/external/sts-helpers}"
export STS_DATA_ROOT="${STS_DATA_ROOT:-${HART_REPO_ROOT}/external/sts-docker-data}"

export STS_BACKUPS_DIR="${STS_BACKUPS_DIR:-${STS_DATA_ROOT}/backups}"
export STS_DATABASE_DIR="${STS_DATABASE_DIR:-${STS_DATA_ROOT}/database}"
export STS_IMAGES_DIR="${STS_IMAGES_DIR:-${STS_DATA_ROOT}/Rolling Stock photos}"

export HART_CAR_CARDS_ROOT="${HART_CAR_CARDS_ROOT:-${HART_REPO_ROOT}/ops/car-cards}"
export HART_CAR_IMAGES_FINAL="${HART_CAR_IMAGES_FINAL:-${HART_CAR_CARDS_ROOT}/car-images/CarImagesFinal}"
export HART_STS_HELPERS="${HART_STS_HELPERS:-${STS_HELPERS_ROOT}}"
export STS_DOCKER="${STS_DOCKER:-${STS_DOCKER_ROOT}}"
export COMPOSE_PROFILES="${COMPOSE_PROFILES:-build}"
export JMRI_LAYOUT="${JMRI_LAYOUT:-hart}"
